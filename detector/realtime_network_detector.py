import os
import time
import pandas as pd
from datetime import datetime, timedelta

# Import custom modules
from modules.config_manager import ConfigManager
from modules.database_manager import DatabaseManager
from modules.monitoring_controller import NetworkMonitoringController
from modules.mongodb_config import get_alerts_collection


def main():
    """Main function for network anomaly detection."""
    
    # Initialize configuration manager
    config_manager = ConfigManager()
    
    # Parse command line arguments and load configuration
    config_file, interface, detector_id, output_dir = config_manager.parse_command_line_args()
    config_manager.load_config_file()
    
    if not config_manager.validate_config():
        return
    
    config_manager.print_config_summary()
    max_iterations = config_manager.max_iterations
    
    # Get log type for this detector from configuration
    def get_detector_log_type(interface, detector_id):
        """Get log type for the specific detector from configuration."""
        try:
            from modules.detector_config_module import DetectorConfigParser
            parser = DetectorConfigParser('detector_config.yaml')
            if parser.load_config():
                for detector_config in parser.detectors:
                    if (detector_config.get('interface') == interface and 
                        detector_config.get('detector_id') == detector_id):
                        return detector_config.get('log_type', 'conn')
        except Exception as e:
            print(f"Warning: Could not load detector configuration: {e}")
        return 'conn'  # Default to conn if config not found
    
    log_type = get_detector_log_type(interface, detector_id)
    
    # Get monitoring configuration from YAML
    def get_monitoring_config():
        """Get monitoring configuration from detector_config.yaml"""
        try:
            from modules.detector_config_module import DetectorConfigParser
            parser = DetectorConfigParser('detector_config.yaml')
            if parser.load_config():
                return {
                    'poll_interval': parser.get_monitoring_config('poll_interval', 1.2),
                    'max_training_iteration': parser.get_monitoring_config('max_training_iteration', 100),
                    'window_size': parser.get_monitoring_config('window_size', 3),
                    'log_file_wait_timeout': parser.get_monitoring_config('log_file_wait_timeout', 60)
                }
        except Exception as e:
            print(f"Warning: Could not load monitoring configuration: {e}")
        return {
            'poll_interval': 1.2,
            'max_training_iteration': 100,
            'window_size': 3,
            'log_file_wait_timeout': 60
        }
    
    monitoring_config = get_monitoring_config()
    
    print(f"Starting {log_type.upper()} log monitoring and anomaly detection for interface {interface}, detector {detector_id}...")
    print(f"Using monitoring config: poll_interval={monitoring_config['poll_interval']}s, max_training={monitoring_config['max_training_iteration']}, window_size={monitoring_config['window_size']}")
    
    # Determine output directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = config_manager.determine_output_directory(current_dir, output_dir)
    
    # Generate file paths
    file_paths = config_manager.get_file_paths(output_dir)
    
    # Get log type for this detector from configuration
    def get_detector_log_type(interface, detector_id):
        """Get log type for the specific detector from configuration."""
        try:
            from modules.detector_config_module import DetectorConfigParser
            parser = DetectorConfigParser('detector_config.yaml')
            if parser.load_config():
                for detector_config in parser.detectors:
                    if (detector_config.get('interface') == interface and 
                        detector_config.get('detector_id') == detector_id):
                        return detector_config.get('log_type', 'conn')
        except Exception as e:
            print(f"Warning: Could not load detector configuration: {e}")
        return 'conn'  # Default to conn if config not found
    
    log_type = get_detector_log_type(interface, detector_id)
    
    print(f"Output directory: {output_dir}")
    print(f"Alerts file: {file_paths['alerts_json']}")
    print(f"Detector ID: {detector_id}")
    print(f"Monitoring type: {log_type.upper()}")
    
    # Test MongoDB connection
    alerts_collection = get_alerts_collection()
    if alerts_collection is None:
        print("WARNING: MongoDB connection failed. Alerts will only be saved to JSON file.")
    else:
        print("MongoDB connection established successfully")
    
    # Initialize monitoring controller with log type and configuration
    controller = NetworkMonitoringController(interface, detector_id, output_dir, log_type)
    
    # Apply monitoring configuration from YAML
    controller.max_training_iteration = monitoring_config['max_training_iteration']
    controller.window_size = monitoring_config['window_size']
    controller.log_file_wait_timeout = monitoring_config['log_file_wait_timeout']
    controller.db_manager.poll_interval = monitoring_config['poll_interval']
    
    # Setup database connection
    controller.db_manager.setup_database()
    
    # Setup log monitoring
    log_file_path = controller.setup_log_monitoring()
    
    # Wait for log file to exist
    if not controller.wait_for_log_file(log_file_path):
        return
    
    try:
        print("Starting monitoring loop...")
        
        while True:
            # Get new data from log monitor
            try:
                new_data = controller.log_monitor.get_new_data()
            except FileNotFoundError:
                print(f"Log file removed, waiting for it to exist...")
                time.sleep(controller.db_manager.poll_interval)
                continue
            except Exception as e:
                print(f"Error getting new data: {e}")
                time.sleep(controller.db_manager.poll_interval)
                continue
            
            # Get current iteration from database
            iteration = controller.db_manager.get_current_iteration()
            
            # Check if we've reached the maximum iterations
            if iteration >= max_iterations:
                print(f"Reached maximum iterations ({max_iterations}), stopping monitoring...")
                break
            
            # Process new iteration if iteration has changed
            if iteration != controller.last_processed_iteration:
                controller.process_new_iteration(iteration)
            
            # Accumulate new data within current iteration
            controller.accumulate_iteration_data(new_data, iteration)
            
            time.sleep(0.1)
            
            # Process latest data for anomaly detection
            if not controller.aggregate_resampled_data.empty:
                latest_data_points = min(30, len(controller.aggregate_resampled_data))
                latest_processed_data = controller.aggregate_resampled_data.tail(latest_data_points).copy()
            else:
                latest_processed_data = pd.DataFrame()
            
            # Get valid rolling mean data
            if not latest_processed_data.empty and 'rolling_mean' in latest_processed_data.columns:
                rolling_mean_series = latest_processed_data['rolling_mean']
                valid_rolling_mean = rolling_mean_series.dropna()
            else:
                valid_rolling_mean = pd.Series()
            
            if len(valid_rolling_mean) > 0:
                # Train model if enough data collected
                controller.train_model_if_ready(iteration, current_dir)
                
                # Show training progress if model not trained yet
                if not controller.model_trained:
                    if iteration > controller.last_printed_iteration:
                        current_synthetic_timestamp = controller.base_time + timedelta(minutes=iteration * 5)
                        print(f"\nCollecting training data - {iteration}/{controller.max_training_iteration} training iteration on simulation timestamp: {current_synthetic_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                        controller.last_printed_iteration = iteration
                
                # Run anomaly detection if model is trained
                if controller.model_trained and controller.anomaly_detection_enabled:
                    controller.run_anomaly_detection(valid_rolling_mean, iteration)
                elif not controller.model_trained:
                    if iteration > controller.last_printed_iteration:
                        print(f"Model not trained yet - Need {controller.max_training_iteration - iteration} more training iterations")
                        controller.last_printed_iteration = iteration
            else:
                # Only print NaN warning once per iteration to avoid spam
                if iteration > controller.last_nan_warning_iteration:
                    print("No valid rolling mean data in latest batch (all NaN values)")
                    controller.last_nan_warning_iteration = iteration
    
    except Exception as e:
        print(f"Error during monitoring: {e}")
    finally:
        # Cleanup resources and save final data
        controller.cleanup()


if __name__ == "__main__":
    main()
