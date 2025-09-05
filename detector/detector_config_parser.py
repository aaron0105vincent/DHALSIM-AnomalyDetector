
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))
from detector_config_module import parse_detector_config


def extract_detector_info(config_file_path):
    """
    Extract detector information from configuration file.
    
    Args:
        config_file_path (str): Path to the detector configuration YAML file
        
    Returns:
        None: Prints detector information to stdout in pipe-delimited format
    """
    try:
        parser = parse_detector_config(config_file_path)
        
        if parser:
            enabled_detectors = parser.get_enabled_detectors()
            
            for detector in enabled_detectors:
                interface = detector.get('interface', '')
                detector_id = detector.get('detector_id', '')
                log_type = detector.get('log_type', 'conn')
                script = detector.get('detector_script', 'realtime_network_detector.py')
                
                # Output in pipe-delimited format for bash parsing
                print(f'{interface}|{detector_id}|{log_type}|{script}')
        else:
            print("Error: Failed to parse detector configuration", file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"Error extracting detector information: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) != 2:
        print("Usage: python3 detector_info_extractor.py <detector_config.yaml>")
        sys.exit(1)
    
    config_file = sys.argv[1]
    
    if not os.path.exists(config_file):
        print(f"Error: Configuration file not found: {config_file}", file=sys.stderr)
        sys.exit(1)
    
    extract_detector_info(config_file)


if __name__ == "__main__":
    main()
