import time
import pandas as pd
from pathlib import Path
import argparse

def get_header_and_data_from_log(filename):
    """Parse Zeek log file and return DataFrame"""
    with open(filename, 'r') as f:
        lines = f.readlines()
    # Find header line from '#fields'
    header_line = next(line for line in lines if line.startswith("#fields"))
    header = header_line.strip().split('\x09')[1:]  # skip '#fields'

    # Get data lines (ignore all lines starting with '#')
    data = [line.strip().split('\x09') for line in lines if not line.startswith("#")]

    # convert to dataframe
    dataframe = pd.DataFrame(data, columns=header)
    return dataframe

def process_zeek_conn_log(log_file_path):
    """
    Process a Zeek connection log file and return DataFrame with ts, id.orig_h, id.resp_h
    
    Args:
        log_file_path (str or Path): Path to the Zeek conn.log file
        
    Returns:
        pd.DataFrame: DataFrame with columns ['ts', 'id.orig_h', 'id.resp_h']
                     Returns None if file doesn't exist or processing fails
    """
    try:
        log_path = Path(log_file_path)
        if not log_path.exists():
            print(f"Log file not found: {log_path}")
            return None
            
        df = get_header_and_data_from_log(log_path)
        
        # Extract only the columns we need
        required_cols = ['ts', 'id.orig_h', 'id.resp_h']
        if all(col in df.columns for col in required_cols):
            result_df = df[required_cols].copy()
            
            # Convert timestamp to numeric
            result_df['ts'] = pd.to_numeric(result_df['ts'], errors='coerce')
            
            return result_df
        else:
            print(f"Required columns {required_cols} not found in log file")
            print(f"Available columns: {df.columns.tolist()}")
            return None
            
    except Exception as e:
        print(f"Error processing file: {e}")
        return None

class ConnLogMonitor:
    """
    Monitor Zeek connection logs continuously and provide processed DataFrames
    """
    def __init__(self, log_file_path, output_dir=None, interface_name="default"):
        self.log_file_path = Path(log_file_path)
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.interface_name = interface_name
        self.position_file = self.output_dir / f"{interface_name}_position.txt"
        self.last_position = 0
        
        
        # Load last position if exists
        if self.position_file.exists():
            try:
                with open(self.position_file, 'r') as f:
                    self.last_position = int(f.read().strip())
            except:
                self.last_position = 0

    def save_position(self, position):
        """Save current file position"""
        with open(self.position_file, 'w') as f:
            f.write(str(position))
        self.last_position = position

    def get_new_data(self):
        """
        Get new data from log file since last read position
        
        Returns:
            pd.DataFrame or None: New data as DataFrame, None if no new data
        """
        if not self.log_file_path.exists():
            raise FileNotFoundError(f"Log file does not exist: {self.log_file_path}")
            
        
        try:
            with open(self.log_file_path, 'r') as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                new_position = f.tell()
                
            if not new_lines:
                return None
                
            # Filter out comment lines and empty lines
            data_lines = [line.strip() for line in new_lines 
                         if line.strip() and not line.startswith('#')]
            
            if not data_lines:
                self.save_position(new_position)
                return None
                
            # Get the full file to extract headers
            full_df = process_zeek_conn_log(self.log_file_path)
            if full_df is None:
                return None
                
            # Parse new data lines using the same structure
            with open(self.log_file_path, 'r') as f:
                lines = f.readlines()
            header_line = next(line for line in lines if line.startswith("#fields"))
            header = header_line.strip().split('\x09')[1:]
            
            # Parse new data
            new_data = [line.split('\x09') for line in data_lines]
            new_df = pd.DataFrame(new_data, columns=header)
            
            # Extract required columns
            required_cols = ['ts', 'id.orig_h', 'id.resp_h']
            if all(col in new_df.columns for col in required_cols):
                result_df = new_df[required_cols].copy()
                result_df['ts'] = pd.to_numeric(result_df['ts'], errors='coerce')
                
                self.save_position(new_position)
                return result_df
            else:
                self.save_position(new_position)
                return None
                
        except Exception as e:
            print(f"Error reading new data: {e}")
            return None

    def monitor_with_callback(self, callback_func, check_interval=5, timeout=None):
        """
        Monitor log file and call callback function with new data
        
        Args:
            callback_func: Function to call with new DataFrame data
            check_interval: Seconds between checks
            timeout: Stop after N seconds of no updates (None = no timeout)
        """
        print(f"Monitoring: {self.log_file_path}")
        
        last_update_time = time.time()
        
        try:
            while True:
                new_data = self.get_new_data()
                current_time = time.time()
                
                if new_data is not None and not new_data.empty:
                    callback_func(new_data)
                    last_update_time = current_time
                
                # Check timeout
                if timeout and (current_time - last_update_time > timeout):
                    print(f"\nNo updates for {timeout}s. Stopping.")
                    break
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\nStopped by user")
        except Exception as e:
            print(f"Error: {e}")

# Backwards compatibility - keep the old class as well
class ConnLogProcessor(ConnLogMonitor):
    """Legacy class for backwards compatibility"""
    def __init__(self, log_file_path, output_dir, interface_name):
        super().__init__(log_file_path, output_dir, interface_name)
        self.processed_dir = self.output_dir / "processed"
        self.processed_dir.mkdir(exist_ok=True)

    def process_and_save(self, batch_number):
        """Process entire log file and save extracted data"""
        try:
            df = process_zeek_conn_log(self.log_file_path)
            if df is not None:
                timestamp = int(time.time())
                output_file = self.processed_dir / f"conn_batch_{batch_number}_{timestamp}.tsv"
                
                with open(output_file, 'w') as f:
                    f.write("#fields\tts\tid.orig_h\tid.resp_h\n")
                    f.write("#types\ttime\taddr\taddr\n")
                    df.to_csv(f, sep='\t', index=False, header=False)
                
                print(f"Saved {len(df)} rows to {output_file.name}")
                return True
            return False
                
        except Exception as e:
            print(f"Error processing file: {e}")
            return False

    def monitor_continuously(self, check_interval=5, timeout=10):
        """Monitor log file for changes and save to files"""
        print(f"Monitoring: {self.log_file_path}")
        print(f"Check interval: {check_interval}s, Timeout: {timeout}s")
        
        batch_number = 1
        last_update_time = time.time()
        
        try:
            while True:
                new_data = self.get_new_data()
                current_time = time.time()
                
                if new_data is not None and not new_data.empty:
                    print(f"Found {len(new_data)} new rows")
                    if self.process_and_save(batch_number):
                        batch_number += 1
                        last_update_time = current_time
                
                # Check timeout
                if current_time - last_update_time > timeout:
                    print(f"\nNo updates for {timeout}s. Stopping.")
                    break
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\nStopped by user")
        except Exception as e:
            print(f"Error: {e}")

def main():
    parser = argparse.ArgumentParser(description='Process Zeek conn.log files')
    parser.add_argument('log_file', help='Path to conn.log file')
    parser.add_argument('output_dir', help='Output directory')
    parser.add_argument('interface', help='Interface name')
    parser.add_argument('--interval', type=int, default=5, help='Check interval (default: 5)')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout (default: 10)')
    
    args = parser.parse_args()
    
    processor = ConnLogProcessor(args.log_file, args.output_dir, args.interface)
    processor.monitor_continuously(args.interval, args.timeout)

if __name__ == "__main__":
    main()
