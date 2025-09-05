import os
import sys
import re
from pathlib import Path


class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self):
        self.config = {}
        self.max_iterations = 300  # Default value
        self.config_file = None
        self.interface = None
        self.detector_id = None
        self.output_dir = None
    
    def parse_command_line_args(self):
        """
        Parse command line arguments.
        
        Returns:
            tuple: (config_file, interface, detector_id, output_dir)
        """
        if len(sys.argv) not in [4, 5]:
            print("Usage: python3 realtime_network_detector2.py config.yaml interface_name detector_location [output_dir]")
            print("  output_dir: optional full path to output directory")
            sys.exit(1)
        
        self.config_file = sys.argv[1]
        self.interface = sys.argv[2]
        self.detector_id = sys.argv[3]
        self.output_dir = sys.argv[4] if len(sys.argv) == 5 else None
        
        return self.config_file, self.interface, self.detector_id, self.output_dir
    
    def load_config_file(self, config_file=None):
        """
        Load configuration from YAML file.
        
        Args:
            config_file (str): Path to configuration file
            
        Returns:
            dict: Configuration dictionary
        """
        if config_file:
            self.config_file = config_file
        
        try:
            with open(self.config_file, 'r') as f:
                config_content = f.read()
                
                # Simple regex search for iterations parameter
                iterations_match = re.search(r'^\s*iterations\s*:\s*(\d+)', config_content, re.MULTILINE)
                self.max_iterations = int(iterations_match.group(1)) if iterations_match else 300
            
            self.config = {'iterations': self.max_iterations}
            return self.config
            
        except FileNotFoundError:
            print(f"Error: Config file '{self.config_file}' not found")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)
    
    def determine_output_directory(self, current_dir, provided_output_dir=None):
        """
        Determine the output directory to use.
        
        Args:
            current_dir (str): Current working directory
            provided_output_dir (str): User-provided output directory
            
        Returns:
            str: Path to output directory
        """
        if provided_output_dir:
            if not os.path.exists(provided_output_dir):
                print(f"Error: Provided output directory does not exist: {provided_output_dir}")
                sys.exit(1)
            return provided_output_dir
        else:
            # Find the most recent output directory (fallback)
            output_base_dirs = [d for d in os.listdir(current_dir) if d.startswith('output_')]
            if output_base_dirs:
                # Sort by creation time and get the most recent
                output_base_dirs.sort(key=lambda x: os.path.getctime(os.path.join(current_dir, x)), reverse=True)
                return os.path.join(current_dir, output_base_dirs[0], self.interface)
            else:
                return os.path.join(current_dir, "output", self.interface)
    
    def get_file_paths(self, output_dir):
        """
        Generate file paths for alerts and logs.
        
        Args:
            output_dir (str): Output directory path
            
        Returns:
            dict: Dictionary containing file paths
        """
        return {
            'alerts_json': os.path.join(output_dir, f"conn_alerts_log_{self.interface}_{self.detector_id}.json"),
            'log_file': os.path.join(output_dir, "conn.log"),
            'aggregate_data': os.path.join(output_dir, f'aggregate_resampled_iteration.csv'),
            'anomaly_scores_log': os.path.join(output_dir, f'anomaly_scores_log_{self.interface}_{self.detector_id}.csv')
        }
    
    def validate_config(self):
        """
        Validate the loaded configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        if not self.config_file:
            print("Error: No configuration file specified")
            return False
        
        if not self.interface:
            print("Error: No interface specified")
            return False
        
        if not self.detector_id:
            print("Error: No detector ID specified")
            return False
        
        if self.max_iterations <= 0:
            print("Error: Invalid max iterations value")
            return False
        
        return True
    
    def print_config_summary(self):
        """Print a summary of the loaded configuration."""
        print(f"Configuration loaded: Max iterations = {self.max_iterations} for interface {self.interface}, detector {self.detector_id}, monitoring CONNECTIONS")


def load_and_validate_config():
    """
    Legacy function to maintain compatibility.
    Load and validate configuration from command line arguments.
    
    Returns:
        tuple: (config_file, interface, detector_id, output_dir, max_iterations)
    """
    config_manager = ConfigManager()
    config_file, interface, detector_id, output_dir = config_manager.parse_command_line_args()
    config_manager.load_config_file()
    
    if not config_manager.validate_config():
        sys.exit(1)
    
    config_manager.print_config_summary()
    
    return config_file, interface, detector_id, output_dir, config_manager.max_iterations
