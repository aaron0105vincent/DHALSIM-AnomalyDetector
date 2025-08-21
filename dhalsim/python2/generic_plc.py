import argparse
import os.path
import sqlite3
import time
from pathlib import Path
import random
import sys
import yaml
import threading
import signal

from basePLC import BasePLC
from entities.attack import TimeAttack, TriggerBelowAttack, TriggerAboveAttack, TriggerBetweenAttack
from entities.control import AboveControl, BelowControl, TimeControl
from dhalsim import py3_logger

class Error(Exception):
    """Base class for exceptions in this module."""

class TagDoesNotExist(Error):
    """Raised when tag you are looking for does not exist"""

class InvalidControlValue(Error):
    """Raised when tag you are looking for does not exist"""

class DatabaseError(Error):
    """Raised when not being able to connect to the database"""

class GenericPLC(BasePLC):
    """
    This class represents a plc. This plc knows what it is connected to by reading the
    yaml file at intermediate_yaml_path and looking at index yaml_index in the plcs section.
    """

    DB_TRIES = 10
    """Amount of times a db query will retry on a exception"""

    UPDATE_RETRIES = 1
    """Amount of times a PLC will try to update its cache"""

    PLC_CACHE_UPDATE_TIME = 0.05
    """ Time in seconds the SCADA server updates its cache"""

    def __init__(self, intermediate_yaml_path, yaml_index):
        self.yaml_index = yaml_index

        with intermediate_yaml_path.open() as yaml_file:
            self.intermediate_yaml = yaml.load(yaml_file, Loader=yaml.FullLoader)

        self.logger = py3_logger.get_logger(self.intermediate_yaml['log_level'])

        self.intermediate_plc = self.intermediate_yaml["plcs"][self.yaml_index]

        # Ensure sensor/actuator lists exist
        self.intermediate_plc.setdefault('sensors', [])
        self.intermediate_plc.setdefault('actuators', [])

        # Controls and attacks
        self.intermediate_controls = self.intermediate_plc['controls']
        self.controls = self.create_controls(self.intermediate_controls)
        self.attacks = self.create_attacks(self.intermediate_plc.get('attacks', []))

        # DB state
        state = {'name': "plant", 'path': self.intermediate_yaml['db_path']}

        # Dependant vs local sensors
        dependant_sensors = [c['dependant'] for c in self.intermediate_controls if c['type'] != 'Time']
        plc_sensors = self.intermediate_plc['sensors']

        # ENIP server setup
        plc_server = {
            'address': self.intermediate_plc['local_ip'],
            'tags': self.generate_real_tags(plc_sensors,
                                            list(set(dependant_sensors) - set(plc_sensors)),
                                            self.intermediate_plc['actuators'])
        }
        plc_protocol = {'name': 'enip', 'mode': 1, 'server': plc_server}

        # Cache initialization
        self.cache = {}
        self.tag_fresh = {}
        self.update_cache_flag = False
        self.plcs_ready = False
        self.plc_run = True
        for tag in set(dependant_sensors) - set(plc_sensors):
            self.cache[tag] = 0.0
            self.tag_fresh[tag] = False

        # Call BasePLC constructor
        self.do_super_construction(plc_protocol, state)

    def do_super_construction(self, plc_protocol, state):
        super(GenericPLC, self).__init__(name=self.intermediate_plc['name'],
                                         state=state, protocol=plc_protocol)

    def send_system_state(self):
        """Override to safely send ENIP state updates"""
        import socket
        try:
            values = []
            for tag in self.tags:
                val = self.get(tag)
                # Decode bytes if needed
                if isinstance(val, bytes):
                    val = val.decode(errors='ignore').strip()
                values.append(val)

            # Sanity checks
            if not self.tags or not values:
                self.logger.warning("Skipping send: empty tags or values.")
                return
            if len(self.tags) != len(values):
                self.logger.error(f"Tag/value mismatch: {len(self.tags)} tags vs {len(values)} values")
                return

            # Safe send to ENIP default port 44818
            ip   = self.intermediate_plc['local_ip']
            port = 44818
            dest = f"{ip}:{port}"
            try:
                self.send_multiple(self.tags, values, dest)
            except (OSError, socket.timeout) as sock_e:
                self.logger.warning(f"ENIP connect/send to {dest} failed: {sock_e}")
            except Exception as e:
                self.logger.error(f"send_multiple() unexpected error to {dest}: {e}")
            
        except Exception as e:
            self.logger.error(f"send_system_state() failed: {e}")

    @staticmethod
    def generate_real_tags(sensors, dependants, actuators):
        real_tags = []
        for sensor in sensors:
            if sensor:
                real_tags.append((sensor, 1, 'REAL'))
        for dep in dependants:
            if dep:
                real_tags.append((dep, 1, 'REAL'))
        for act in actuators:
            if act:
                real_tags.append((act, 1, 'REAL'))
        return tuple(real_tags)

    @staticmethod
    def generate_tags(taggable):
        tags = []
        for tag in (taggable or []):
            if tag:
                tags.append((tag, 1))
        return tags

    @staticmethod
    def create_controls(controls_list):
        ret = []
        for control in controls_list:
            t = control['type'].lower()
            if t == 'above':
                ret.append(AboveControl(control['actuator'], control['action'],
                                         control['dependant'], control['value']))
            elif t == 'below':
                ret.append(BelowControl(control['actuator'], control['action'],
                                         control['dependant'], control['value']))
            elif t == 'time':
                ret.append(TimeControl(control['actuator'], control['action'], control['value']))
        return ret

    @staticmethod
    def create_attacks(attack_list):
        attacks = []
        for attack in attack_list:
            typ = attack['trigger']['type'].lower()
            if typ == 'time':
                attacks.append(TimeAttack(attack['name'], attack['actuator'], attack['command'],
                                          attack['trigger']['start'], attack['trigger']['end']))
            elif typ == 'above':
                attacks.append(TriggerAboveAttack(attack['name'], attack['actuator'], attack['command'],
                                                   attack['trigger']['sensor'], attack['trigger']['value']))
            elif typ == 'below':
                attacks.append(TriggerBelowAttack(attack['name'], attack['actuator'], attack['command'],
                                                   attack['trigger']['sensor'], attack['trigger']['value']))
            elif typ == 'between':
                attacks.append(TriggerBetweenAttack(attack['name'], attack['actuator'], attack['command'],
                                                     attack['trigger']['sensor'],
                                                     attack['trigger']['lower_value'], attack['trigger']['upper_value']))
        return attacks

    def pre_loop(self, sleep=0.5):
        signal.signal(signal.SIGINT, self.sigint_handler)
        signal.signal(signal.SIGTERM, self.sigint_handler)
        self.logger.debug(self.intermediate_plc['name'] + ' enters pre_loop')
        self.db_sleep_time = random.uniform(0.01, 0.1)

        sensors = self.generate_tags(self.intermediate_plc['sensors'])
        actuators = self.generate_tags(self.intermediate_plc['actuators'])
        values = [float(self.get(tag)) for tag in sensors] + [int(self.get(tag)) for tag in actuators]

        noise_scale = self.intermediate_yaml['noise_scale']
        BasePLC.set_parameters(self, sensors, actuators, values,
                               self.intermediate_plc['local_ip'], noise_scale)
        self.cache_updated = False
        time.sleep(sleep)

    def get_tag(self, tag):
        if tag in self.intermediate_plc['sensors'] or tag in self.intermediate_plc['actuators']:
            return float(self.get((tag,1)))
        if tag in self.cache:
            return self.cache[tag]
        self.logger.warning(f"Cache miss in {self.intermediate_plc['name']} for tag {tag}")
        for i, plc_data in enumerate(self.intermediate_yaml['plcs']):
            if i == self.yaml_index:
                continue
            if tag in plc_data['sensors'] or tag in plc_data['actuators']:
                return float(self.receive((tag,1), plc_data['public_ip']))
        raise TagDoesNotExist(tag)

    def get_tag_for_cache(self, tag, plc_ip, cache_update_time):
        for _ in range(self.UPDATE_RETRIES):
            try:
                self.cache[tag] = float(self.receive((tag,1), plc_ip))
                return True
            except Exception as e:
                self.logger.info(f"{self.intermediate_plc['name']} receive {tag} failed: {e}")
                if self.update_cache_flag:
                    time.sleep(cache_update_time)
                    continue
                return False
        return False

    def update_cache(self, cache_update_time):
        while self.update_cache_flag:
            for tag in list(self.cache.keys()):
                for i, plc_data in enumerate(self.intermediate_yaml['plcs']):
                    if i == self.yaml_index:
                        continue
                    if tag in plc_data['sensors'] or tag in plc_data['actuators']:
                        start = self.get_master_clock()
                        ok = self.get_tag_for_cache(tag, plc_data['public_ip'], cache_update_time)
                        if self.get_master_clock() == start:
                            self.tag_fresh[tag] = ok
                        if not ok:
                            self.logger.info(f"Warning: Cache for tag {tag} could not be updated")
                            self.tag_fresh[tag] = True

    def set_tag(self, tag, value):
        if isinstance(value, str) and value.lower() in ('closed','open'):
            value = 0 if value.lower()=='closed' else 1
        else:
            self.logger.debug(f'Pump speed: {value}')
            if self.intermediate_yaml['simulator']=='wntr':
                self.logger.error('Pump speed only supported by epynet')
                raise InvalidControlValue(value)
        if tag in self.intermediate_plc['sensors'] or tag in self.intermediate_plc['actuators']:
            self.set((tag,1), value)
        else:
            raise TagDoesNotExist(f"{tag} cannot be set from {self.intermediate_plc['name']}")

    def db_query(self, query, write=False, parameters=None):
        for i in range(self.DB_TRIES):
            try:
                conn = sqlite3.connect(self.intermediate_yaml['db_path'], timeout=30.0)
                conn.execute("PRAGMA journal_mode=WAL;")
                with conn:
                    cur = conn.cursor()
                    cur.execute(query, parameters or ())
                    conn.commit()
                    if not write:
                        return cur.fetchone()[0]
                    return
            except sqlite3.OperationalError as exc:
                self.logger.info(f"Failed to connect to db: {exc}. Retrying {self.DB_TRIES-i-1} times.")
                time.sleep(self.db_sleep_time)
        self.logger.error(f"Failed to connect after {self.DB_TRIES} tries.")
        raise DatabaseError("DB query failed")

    def get_master_clock(self):
        return self.db_query("SELECT time FROM master_time WHERE id IS 1", False)

    def get_sync(self, flag):
        return self.db_query("SELECT flag FROM sync WHERE name IS ?", False,
                              (self.intermediate_plc['name'],)) == flag

    def set_sync(self, flag):
        self.db_query("UPDATE sync SET flag=? WHERE name IS ?", True,
                      (int(flag), self.intermediate_plc['name']))

    def set_attack_flag(self, flag, attack_name):
        self.db_query("UPDATE attack SET flag=? WHERE name IS ?", True,
                      (int(flag), attack_name))

    def stop_cache_update(self):
        self.update_cache_flag = False

    def sigint_handler(self, sig, frame):
        self.logger.debug('PLC shutdown commencing.')
        self.stop_cache_update()
        self.plc_run = False
        self.logger.debug('PLC shutdown finished.')
        sys.exit(0)

    def main_loop(self, sleep=0.5, test_break=False):
        self.logger.debug(self.intermediate_plc['name'] + ' enters main_loop')
        while self.plc_run:
            if not self.plcs_ready:
                self.logger.debug(f"PLC {self.intermediate_plc['name']} starting update cache thread")
                self.plcs_ready = True
                self.update_cache_flag = True
                threading.Thread(target=self.update_cache,
                                 args=(self.PLC_CACHE_UPDATE_TIME,),
                                 daemon=True).start()
            while not self.get_sync(0): 
                time.sleep(0.001)
            self.send_system_state()
            self.set_sync(1)
            while not self.get_sync(2): 
                time.sleep(0.001)
            for t in self.tag_fresh: self.tag_fresh[t] = False
            while not all(self.tag_fresh.values()): 
                time.sleep(0.001)
            clock = self.get_master_clock()
            for control in self.controls: control.apply(self)
            for attack in self.attacks: attack.apply(self)
            self.set_sync(3)
            if test_break: break


def is_valid_file(parser_instance, arg):
    if not os.path.exists(arg):
        parser_instance.error(arg + " does not exist")
    return arg

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Start everything for a plc')
    parser.add_argument(dest="intermediate_yaml", help="intermediate yaml file", metavar="FILE", 
                        type=lambda x: is_valid_file(parser, x))
    parser.add_argument(dest="index", help="Index of PLC in intermediate yaml", type=int,
                        metavar="N")
    args = parser.parse_args()
    GenericPLC(intermediate_yaml_path=Path(args.intermediate_yaml), yaml_index=args.index)

