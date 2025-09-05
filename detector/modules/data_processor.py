import pandas as pd
from datetime import datetime, timedelta
from .connection_processor import filter_entity_connections


def extract_ip_pairs_from_connections(filtered_connections):
    """
    Extract IP pairs information from filtered connections for alert enrichment.
    Handles both conn log format (id.orig_h, id.resp_h) and ARP log format (orig_h, resp_h).
    
    Args:
        filtered_connections (pd.DataFrame): DataFrame containing connection data
        
    Returns:
        list: List of dictionaries containing IP pair information
    """
    unique_pairs = []
    
    for _, connection_row in filtered_connections.iterrows():
        # Check for conn log format first (id.orig_h, id.resp_h)
        if 'id.orig_h' in connection_row and 'id.resp_h' in connection_row:
            pair_info = {
                'IP': connection_row['id.orig_h'],
                'communicateswith': connection_row['id.resp_h'],
                'direction': 'outbound'
            }
            unique_pairs.append(pair_info)
        # Check for ARP log format (orig_h, resp_h)
        elif 'orig_h' in connection_row and 'resp_h' in connection_row:
            pair_info = {
                'IP': connection_row['orig_h'],
                'communicateswith': connection_row['resp_h'],
                'direction': 'outbound'
            }
            unique_pairs.append(pair_info)
    
    return unique_pairs


def process_iteration_data(new_data, iteration, entity_ip='192.168.1.1', base_time=None):
    """
    Process new data for a single iteration, including filtering and timestamp generation.
    
    Args:
        new_data (pd.DataFrame): New connection data from Zeek
        iteration (int): Current iteration number
        entity_ip (str): IP address to filter connections for
        base_time (datetime): Base time for synthetic timestamp generation
        
    Returns:
        tuple: (total_connections, synthetic_timestamp, new_resampled_data, unique_pairs)
    """
    if base_time is None:
        base_time = datetime(2025, 1, 1)
    
    # Filter connections for the traffic of entity and count connections
    filtered_connections = filter_entity_connections(new_data, entity_ip)
    total_connections = len(filtered_connections)
    
    # Map synthetic timestamp (iteration to 5-minute interval)
    synthetic_timestamp = base_time + timedelta(minutes=iteration * 5)
    
    # Create resampled data DataFrame
    new_resampled_data = pd.DataFrame({
        'total_connections': [total_connections],
        'iteration': [iteration]
    }, index=[synthetic_timestamp])
    
    # Set the index name for proper CSV column headers
    new_resampled_data.index.name = 'timestamp'
    
    # Extract IP pairs for alert enrichment
    unique_pairs = extract_ip_pairs_from_connections(filtered_connections)
    
    return total_connections, synthetic_timestamp, new_resampled_data, unique_pairs


def update_aggregate_data(aggregate_resampled_data, new_resampled_data, iteration, window_size=3):
    """
    Update aggregate dataset with new data and calculate rolling mean.
    
    Args:
        aggregate_resampled_data (pd.DataFrame): Existing aggregate data
        new_resampled_data (pd.DataFrame): New data to add
        iteration (int): Current iteration number
        window_size (int): Window size for rolling mean calculation
        
    Returns:
        pd.DataFrame: Updated aggregate data with rolling mean
    """
    # Append new data to aggregate dataset
    if aggregate_resampled_data.empty:
        aggregate_resampled_data = new_resampled_data.copy()
    else:
        # Append new data to existing aggregate
        aggregate_resampled_data = pd.concat([aggregate_resampled_data, new_resampled_data])
        # Remove duplicate data and sort by timestamp
        aggregate_resampled_data = aggregate_resampled_data[~aggregate_resampled_data.index.duplicated(keep='last')]
        aggregate_resampled_data = aggregate_resampled_data.sort_index()
    
    # Apply rolling mean to the full aggregate dataset
    aggregate_resampled_data['rolling_mean'] = aggregate_resampled_data['total_connections'].rolling(window=window_size).mean()
    
    return aggregate_resampled_data
