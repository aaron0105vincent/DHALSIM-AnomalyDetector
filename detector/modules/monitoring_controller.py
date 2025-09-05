import os
import time
import pandas as pd
from datetime import datetime, timedelta

from .conn_log_processor import ConnLogMonitor
from .arp_log_processor import ArpLogMonitor
from .data_processor import process_iteration_data, update_aggregate_data
from .sarima_detector import SarimaAnomalyDetector
from .alert_manager import AlertManager
from .database_manager import DatabaseManager


class NetworkMonitoringController:
    """Main controller for network monitoring and anomaly detection."""
    
    def __init__(self, interface, detector_id, output_dir, log_type='conn', entity_ip='192.168.1.1'):
        """
        Initialize monitoring controller.
        
        Args:
            interface (str): Network interface name
            detector_id (str): Detector identifier
            output_dir (str): Output directory path
            log_type (str): Type of log to monitor ('conn', 'arp', etc.)
            entity_ip (str): Entity IP address to monitor
        """
        self.interface = interface
        self.detector_id = detector_id
        self.output_dir = output_dir
        self.log_type = log_type
        self.entity_ip = entity_ip
        self.base_time = datetime(2025, 1, 1)
        
        # Initialize components
        self.db_manager = DatabaseManager()
        self.alert_manager = AlertManager()
        self.sarima_detector = SarimaAnomalyDetector()
        self.log_monitor = None
        
        # Monitoring state
        self.aggregate_resampled_data = pd.DataFrame()
        self.aggregate_ip_pairs_mapping = {}
        self.last_processed_iteration = -1
        self.iteration_total_count = 0
        self.iteration_unique_pairs = []
        self.last_finalized_count = 0
        self.last_printed_iteration = -1
        self.last_nan_warning_iteration = -1
        
        # Configuration
        self.window_size = 3
        self.max_training_iteration = 100
        self.model_trained = False
        self.anomaly_detection_enabled = False
        self.anomaly_threshold = 0
        self.log_file_wait_timeout = 60
    
    def setup_log_monitoring(self):
        """Setup log file monitoring based on log type."""
        log_file_path = os.path.join(self.output_dir, f"{self.log_type}.log")
        
        # Choose appropriate log monitor based on log type
        if self.log_type == 'arp':
            self.log_monitor = ArpLogMonitor(log_file_path, self.output_dir, self.interface)
            alerts_json_file = os.path.join(self.output_dir, f"arp_alerts_log_{self.interface}_{self.detector_id}.json")
        else:  # Default to conn for other types (conn, cip, dns, enip, reporter)
            self.log_monitor = ConnLogMonitor(log_file_path, self.output_dir, self.interface)
            alerts_json_file = os.path.join(self.output_dir, f"conn_alerts_log_{self.interface}_{self.detector_id}.json")
        
        # Set up alert manager
        self.alert_manager = AlertManager(alerts_json_file)
        
        return log_file_path
    
    def wait_for_log_file(self, log_file_path):
        """
        Wait for log file to exist before starting monitoring.
        
        Args:
            log_file_path (str): Path to log file
            
        Returns:
            bool: True if file exists, False if timeout
        """
        print(f"Waiting for {self.log_type}.log file: {log_file_path}")
        log_wait_start = time.time()
        
        while not os.path.exists(log_file_path):
            if time.time() - log_wait_start > self.log_file_wait_timeout:
                print(f"ERROR: Log file {log_file_path} did not appear within {self.log_file_wait_timeout} seconds")
                return False
            print(f"Log file not found, waiting... ({int(time.time() - log_wait_start)}s)")
            time.sleep(2)
        
        print(f"{self.log_type}.log file found: {log_file_path}")
        return True
    
    def process_new_iteration(self, iteration):
        """
        Process data for a new iteration.
        
        Args:
            iteration (int): Current iteration number
        """
        if self.last_processed_iteration >= 0:
            # Finalize previous iteration
            synthetic_timestamp = self.base_time + timedelta(minutes=self.last_processed_iteration * 5)
            
            # Create resampled data for the finalized iteration
            new_resampled_data = pd.DataFrame({
                'total_connections': [self.iteration_total_count],
                'iteration': [self.last_processed_iteration]
            }, index=[synthetic_timestamp])
            new_resampled_data.index.name = 'timestamp'
            
            # Update IP pairs mapping
            new_ip_pairs_mapping = {synthetic_timestamp: self.iteration_unique_pairs}
            self.aggregate_ip_pairs_mapping.update(new_ip_pairs_mapping)
            
            # Update aggregate dataset
            self.aggregate_resampled_data = update_aggregate_data(
                self.aggregate_resampled_data, new_resampled_data, 
                self.last_processed_iteration, self.window_size
            )
            
            self.last_finalized_count = self.iteration_total_count
            print(f"\nFinalized iteration {self.last_processed_iteration}: {self.iteration_total_count} connection entries")
        
        # Reset counters for new iteration
        self.iteration_total_count = 0
        self.iteration_unique_pairs = []
        self.last_processed_iteration = iteration
    
    def accumulate_iteration_data(self, new_data, iteration):
        """
        Accumulate data within current iteration.
        
        Args:
            new_data (pd.DataFrame): New data from log monitor
            iteration (int): Current iteration
        """
        if new_data is not None:
            current_count, _, _, unique_pairs = process_iteration_data(
                new_data, iteration, self.entity_ip, self.base_time
            )
            
            self.iteration_total_count += current_count
            self.iteration_unique_pairs.extend(unique_pairs)
            print(".", end='')  # Progress indicator
    
    def train_model_if_ready(self, iteration, current_dir):
        """
        Train SARIMA model if enough data is collected.
        
        Args:
            iteration (int): Current iteration
            current_dir (str): Current directory path
        """
        if not self.model_trained and iteration >= self.max_training_iteration:
            print(f"TRAINING MODEL - Collected samples for {iteration}, training SARIMA model...")
            
            # Train the model
            training_data = self.aggregate_resampled_data['rolling_mean']
            save_dir = os.path.join(current_dir, 'model')
            model_name = f'sarima_{self.log_type}_{self.interface}_{self.detector_id}'
            
            if self.sarima_detector.train_model(training_data, save_dir, model_name):
                self.model_trained = True
                self.anomaly_detection_enabled = True
                print(f"Model Training Successful for {self.detector_id} ({self.log_type.upper()}) - Anomaly detection enabled")
    
    def run_anomaly_detection(self, valid_rolling_mean, iteration):
        """
        Run anomaly detection on the latest data.
        
        Args:
            valid_rolling_mean (pd.Series): Valid rolling mean data
            iteration (int): Current iteration
        """
        if not (self.model_trained and self.anomaly_detection_enabled):
            return
        
        if iteration <= self.last_printed_iteration:
            return
        
        # Get anomaly scores
        latest_data = valid_rolling_mean[-1:]
        anomaly_scores = self.sarima_detector.get_anomaly_scores(latest_data)
        
        if anomaly_scores is None:
            return
        
        # Check for anomalies
        alerted_scores = anomaly_scores[abs(anomaly_scores.iloc[:, 0]) > self.anomaly_threshold]
        anomaly_detected = len(alerted_scores) > 0
        
        # Calculate timestamp
        current_synthetic_timestamp = self.base_time + timedelta(minutes=iteration * 5)
        
        # Log anomaly scores
        self.alert_manager.log_anomaly_scores(
            iteration, 
            current_synthetic_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            anomaly_scores
        )
        
        # Print progress
        latest_rolling_mean = valid_rolling_mean.iloc[-1] if len(valid_rolling_mean) > 0 else 0.0
        latest_anomaly_score = abs(anomaly_scores.iloc[:, 0]).max() if len(anomaly_scores) > 0 else 0.0
        print(f"[Iter {iteration} @ {current_synthetic_timestamp.strftime('%Y-%m-%d %H:%M:%S')}] : {self.last_finalized_count} | Rolling Mean: {latest_rolling_mean:.3f} | Anomaly Score: {latest_anomaly_score:.3f} | Anomaly: {anomaly_detected}")
        
        # Process alerts if anomalies detected
        if anomaly_detected:
            print(f"!!ANOMALY DETECTED!!: {len(alerted_scores)} anomalies found on iteration {iteration}")
            self.alert_manager.process_anomaly_alerts(
                alerted_scores, valid_rolling_mean, self.aggregate_ip_pairs_mapping,
                self.detector_id, self.last_finalized_count, iteration, self.entity_ip
            )
        
        self.last_printed_iteration = iteration
    
    def cleanup(self):
        """Cleanup resources and save final data."""
        # Save final aggregate data
        self.aggregate_resampled_data.to_csv(
            os.path.join(self.output_dir, f'aggregate_resampled_iteration_{self.last_processed_iteration}.csv'), 
            index=True
        )
        
        # Save anomaly scores log
        anomaly_log_path = os.path.join(self.output_dir, f'anomaly_scores_log_{self.interface}_{self.detector_id}.csv')
        records_saved = self.alert_manager.save_anomaly_scores_log(anomaly_log_path)
        
        if records_saved > 0:
            print(f"Anomaly scores log saved to {anomaly_log_path} ({records_saved} entries)")
        else:
            print("No anomaly scores to save")
        
        # Close database connection
        self.db_manager.close()
        
        # Remove position file
        if self.log_monitor and hasattr(self.log_monitor, 'position_file'):
            if os.path.exists(self.log_monitor.position_file):
                os.remove(self.log_monitor.position_file)
                print("Position file removed.")
            else:
                print("Position file does not exist, nothing to remove.")
