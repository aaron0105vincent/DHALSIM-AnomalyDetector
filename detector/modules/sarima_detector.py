import os
from merlion.utils.time_series import TimeSeries
from merlion.models.anomaly.forecast_based.sarima import SarimaDetector, SarimaDetectorConfig


class SarimaAnomalyDetector:
    """Wrapper class for SARIMA-based anomaly detection."""
    
    def __init__(self, order=(2, 1, 2), seasonal_order=(1, 1, 1, 12)):
        """
        Initialize SARIMA detector configuration.
        
        Args:
            order (tuple): ARIMA order (p,d,q)
            seasonal_order (tuple): Seasonal ARIMA order
        """
        self.order = order
        self.seasonal_order = seasonal_order
        self.model = None
        self.is_trained = False
    
    def train_model(self, training_data, save_dir=None, model_name=None):
        """
        Train SARIMA model using the provided training data.
        
        Args:
            training_data (pd.Series): Training data with rolling mean
            save_dir (str): Directory to save the trained model
            model_name (str): Name for the saved model
            
        Returns:
            bool: True if training successful, False otherwise
        """
        try:
            # Convert to Merlion TimeSeries
            training_ts = TimeSeries.from_pd(training_data.dropna())
            
            # Create and configure SARIMA detector
            config = SarimaDetectorConfig(
                order=self.order,
                seasonal_order=self.seasonal_order,
                threshold=None  # Manual Threshold
            )
            self.model = SarimaDetector(config)
            self.model.train(training_ts)
            
            # Save the trained model if directory and name provided
            if save_dir and model_name:
                os.makedirs(save_dir, exist_ok=True)
                self.model.save(dirname=os.path.join(save_dir, model_name))
            
            self.is_trained = True
            return True
            
        except Exception as e:
            print(f"Error training SARIMA model: {e}")
            return False
    
    def get_anomaly_scores(self, data):
        """
        Get anomaly scores for the provided data.
        
        Args:
            data (pd.Series): Data to analyze for anomalies
            
        Returns:
            pd.DataFrame: Anomaly scores or None if model not trained
        """
        if not self.is_trained or self.model is None:
            print("Model not trained. Please train the model first.")
            return None
        
        try:
            sample_data = TimeSeries.from_pd(data)
            # Take the latest data point
            sample_data = sample_data[-1:]
            anomaly_scores = self.model.get_anomaly_label(sample_data).to_pd()
            return anomaly_scores
        except Exception as e:
            print(f"Error getting anomaly scores: {e}")
            return None
    
    def load_model(self, model_path):
        """
        Load a pre-trained model from disk.
        
        Args:
            model_path (str): Path to the saved model
            
        Returns:
            bool: True if loading successful, False otherwise
        """
        try:
            config = SarimaDetectorConfig(
                order=self.order,
                seasonal_order=self.seasonal_order,
                threshold=None
            )
            self.model = SarimaDetector.load(dirname=model_path, config=config)
            self.is_trained = True
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False


def train_sarima_model(aggregate_resampled_data, current_dir, interface, detector_id):
    """
    Legacy function to maintain compatibility.
    Train SARIMA model using the aggregate data.
    
    Args:
        aggregate_resampled_data (pd.DataFrame): Training data
        current_dir (str): Current directory path
        interface (str): Network interface name
        detector_id (str): Detector identifier
        
    Returns:
        SarimaDetector: Trained SARIMA model or None if training failed
    """
    detector = SarimaAnomalyDetector()
    
    # Get rolling mean data for training
    training_data = aggregate_resampled_data['rolling_mean']
    
    # Set up save directory and model name
    save_dir = os.path.join(current_dir, 'model')
    model_name = f'sarima_conn_{interface}_{detector_id}'
    
    # Train the model
    if detector.train_model(training_data, save_dir, model_name):
        print(f"Model Training Successful for {detector_id} (CONNECTION) - Anomaly detection enabled")
        return detector.model
    else:
        print(f"Error training model for {detector_id}")
        return None
