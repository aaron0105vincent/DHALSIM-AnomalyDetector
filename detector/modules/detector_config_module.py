import yaml
import os
import sys
from typing import Dict, List, Any, Optional


class DetectorConfigParser:
    """Parser for enhanced detector configuration files."""
    
    def __init__(self, config_file: str):
        """
        Initialize the configuration parser.
        
        Args:
            config_file (str): Path to the detector configuration YAML file
        """
        self.config_file = config_file
        self.config = {}
        self.detectors = []
        self.log_types = {}
        self.monitoring_config = {}
        
    def load_config(self) -> bool:
        """
        Load configuration from YAML file.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f) or {}
            
            # Parse sections
            self.detectors = self.config.get('detectors', [])
            self.log_types = self.config.get('log_types', {})
            self.monitoring_config = self.config.get('monitoring', {})
            
            return True
            
        except FileNotFoundError:
            print(f"Error: Configuration file not found: {self.config_file}")
            return False
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {e}")
            return False
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return False
    
    def get_enabled_detectors(self) -> List[Dict[str, Any]]:
        """
        Get list of enabled detectors.
        
        Returns:
            List[Dict]: List of enabled detector configurations
        """
        return [detector for detector in self.detectors if detector.get('enabled', True)]
    
    def get_detectors_by_log_type(self, log_type: str) -> List[Dict[str, Any]]:
        """
        Get detectors filtered by log type.
        
        Args:
            log_type (str): Log type to filter by
            
        Returns:
            List[Dict]: List of detectors for the specified log type
        """
        return [detector for detector in self.get_enabled_detectors() 
                if detector.get('log_type') == log_type]
    
    def get_detectors_by_interface(self, interface: str) -> List[Dict[str, Any]]:
        """
        Get detectors filtered by interface.
        
        Args:
            interface (str): Interface to filter by
            
        Returns:
            List[Dict]: List of detectors for the specified interface
        """
        return [detector for detector in self.get_enabled_detectors() 
                if detector.get('interface') == interface]
    
    def get_log_type_info(self, log_type: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific log type.
        
        Args:
            log_type (str): Log type name
            
        Returns:
            Optional[Dict]: Log type configuration or None if not found
        """
        return self.log_types.get(log_type)
    
    def get_available_log_types(self) -> List[str]:
        """
        Get list of available log types.
        
        Returns:
            List[str]: List of available log type names
        """
        return list(self.log_types.keys())
    
    def get_monitoring_config(self, key: str, default: Any = None) -> Any:
        """
        Get monitoring configuration value.
        
        Args:
            key (str): Configuration key
            default (Any): Default value if key not found
            
        Returns:
            Any: Configuration value
        """
        return self.monitoring_config.get(key, default)
    
    def validate_config(self) -> bool:
        """
        Validate the loaded configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        if not self.detectors:
            print("Error: No detectors configured")
            return False
        
        # Validate each detector
        for i, detector in enumerate(self.detectors):
            if not detector.get('interface'):
                print(f"Error: Detector {i+1} missing 'interface' field")
                return False
            
            if not detector.get('detector_id'):
                print(f"Error: Detector {i+1} missing 'detector_id' field")
                return False
            
            log_type = detector.get('log_type')
            if log_type and log_type not in self.log_types:
                print(f"Error: Detector {i+1} uses undefined log_type '{log_type}'")
                return False
        
        return True
    
    def print_config_summary(self):
        """Print a summary of the loaded configuration."""
        enabled_detectors = self.get_enabled_detectors()
        print(f"[*] Loaded detector configuration: {len(enabled_detectors)} enabled detectors")
        
        # Group by log type
        log_type_groups = {}
        for detector in enabled_detectors:
            log_type = detector.get('log_type', 'unknown')
            if log_type not in log_type_groups:
                log_type_groups[log_type] = []
            log_type_groups[log_type].append(detector)
        
        for log_type, detectors in log_type_groups.items():
            log_info = self.get_log_type_info(log_type)
            log_desc = log_info.get('description', 'Unknown') if log_info else 'Unknown'
            print(f"[*] {log_type.upper()} Log Monitors ({log_desc}):")
            for detector in detectors:
                print(f"    {detector['detector_id']} -> {detector['interface']} ({detector.get('detector_script', 'default')})")


def parse_detector_config(config_file: str) -> Optional[DetectorConfigParser]:
    """
    Parse detector configuration file.
    
    Args:
        config_file (str): Path to configuration file
        
    Returns:
        Optional[DetectorConfigParser]: Parser instance or None if failed
    """
    parser = DetectorConfigParser(config_file)
    if parser.load_config() and parser.validate_config():
        return parser
    return None


if __name__ == "__main__":
    # Test the parser
    if len(sys.argv) != 2:
        print("Usage: python3 detector_config_parser.py <detector_config.yaml>")
        sys.exit(1)
    
    config_file = sys.argv[1]
    parser = parse_detector_config(config_file)
    
    if parser:
        parser.print_config_summary()
        print(f"\nAvailable log types: {', '.join(parser.get_available_log_types())}")
    else:
        print("Failed to load configuration")
        sys.exit(1)
