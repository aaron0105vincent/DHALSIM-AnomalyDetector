import pandas as pd
from .connection_processor import write_alert as write_alert_module
from .mongodb_config import get_alerts_collection


class AlertManager:
    """Manages alert creation, formatting, and logging."""
    
    def __init__(self, alerts_json_file=None):
        """
        Initialize alert manager.
        
        Args:
            alerts_json_file (str): Path to JSON file for alert logging
        """
        self.alerts_json_file = alerts_json_file
        self._first_alert = True
        self.anomaly_scores_log = []
    
    def create_alert_document(self, pair_info, detector_id, anomaly_score, actual_value, 
                            total_count, iteration, timestamp_idx, detection_algorithm="SARIMA"):
        """
        Create an alert document for MongoDB.
        
        Args:
            pair_info (dict): IP pair information
            detector_id (str): Detector identifier
            anomaly_score (float): Anomaly score
            actual_value (float): Actual value
            total_count (int): Total connections count
            iteration (int): Current iteration
            timestamp_idx: Timestamp index
            detection_algorithm (str): Detection algorithm name
            
        Returns:
            dict: Alert document
        """
        detector_name = f"SarimaDetector_{detector_id}"
        
        return {
            "IP": pair_info['IP'],
            "communicateswith": pair_info['communicateswith'],
            "direction": pair_info['direction'],
            "detector": detector_name,
            "alertorigin": detector_id,
            "anomaly_score": anomaly_score,
            "actual_value": actual_value,
            "detection_algorithm": detection_algorithm,
            "synthetic_timestamp": timestamp_idx.strftime('%Y-%m-%d %H:%M:%S'),
            "iteration": iteration,
        }
    
    def write_alert(self, alert_doc):
        """
        Write alert to storage systems.
        
        Args:
            alert_doc (dict): Alert document to write
        """
        self._first_alert = write_alert_module(
            alert_doc, 
            get_alerts_collection, 
            self.alerts_json_file, 
            self._first_alert
        )
    
    def process_anomaly_alerts(self, alerted_scores, valid_rolling_mean, aggregate_ip_pairs_mapping,
                             detector_id, last_finalized_count, iteration, entity_ip='192.168.1.1'):
        """
        Process and create alerts for detected anomalies.
        
        Args:
            alerted_scores (pd.DataFrame): Scores that exceeded threshold
            valid_rolling_mean (pd.Series): Valid rolling mean data
            aggregate_ip_pairs_mapping (dict): IP pairs mapping by timestamp
            detector_id (str): Detector identifier
            last_finalized_count (int): Last finalized connection count
            iteration (int): Current iteration
            entity_ip (str): Entity IP address for fallback
        """
        for idx, row in alerted_scores.iterrows():
            anomaly_score = float(row.iloc[0])
            actual_value = float(valid_rolling_mean.loc[idx]) if idx in valid_rolling_mean.index else 0.0
            
            # Get IP pairs for this timestamp
            timestamp_pairs = aggregate_ip_pairs_mapping.get(idx, [])
            
            if timestamp_pairs:
                # Create separate alerts for each IP pair at this timestamp
                for pair_info in timestamp_pairs:
                    alert_doc = self.create_alert_document(
                        pair_info, detector_id, anomaly_score, actual_value, 
                        last_finalized_count, iteration, idx
                    )
                    self.write_alert(alert_doc)
            else:
                # Fallback: create alert without specific IP pair info
                fallback_pair_info = {
                    'IP': entity_ip,
                    'communicateswith': 'unknown',
                    'direction': 'unknown'
                }
                alert_doc = self.create_alert_document(
                    fallback_pair_info, detector_id, anomaly_score, actual_value,
                    last_finalized_count, iteration, idx
                )
                self.write_alert(alert_doc)
    
    def log_anomaly_scores(self, iteration, timestamp, anomaly_scores):
        """
        Log anomaly scores for later analysis.
        
        Args:
            iteration (int): Current iteration
            timestamp (str): Timestamp string
            anomaly_scores (pd.DataFrame): Anomaly scores
        """
        self.anomaly_scores_log.append({
            'iteration': iteration,
            'timestamp': timestamp,
            'anomaly_scores': anomaly_scores.to_dict(orient='records')
        })
    
    def save_anomaly_scores_log(self, output_path):
        """
        Save accumulated anomaly scores to CSV file.
        
        Args:
            output_path (str): Path to save the CSV file
            
        Returns:
            int: Number of records saved
        """
        if not self.anomaly_scores_log:
            return 0
        
        # Convert to DataFrame for CSV export
        anomaly_df_records = []
        for log_data in self.anomaly_scores_log:
            for score_record in log_data['anomaly_scores']:
                anomaly_df_records.append({
                    'iteration': log_data['iteration'],
                    'timestamp': log_data['timestamp'],
                    'anomaly_score': score_record.get('anom_score', 0.0),
                    'abs_anomaly_score': abs(score_record.get('anom_score', 0.0))
                })
        
        if anomaly_df_records:
            anomaly_df = pd.DataFrame(anomaly_df_records)
            anomaly_df.to_csv(output_path, index=False)
            return len(anomaly_df_records)
        
        return 0


# Legacy function for backward compatibility
def create_alert_document(pair_info, detector_id, anomaly_score, actual_value, total_count, iteration, idx):
    """
    Legacy function to maintain compatibility.
    Create an alert document for MongoDB.
    """
    alert_manager = AlertManager()
    return alert_manager.create_alert_document(
        pair_info, detector_id, anomaly_score, actual_value, 
        total_count, iteration, idx
    )
