import json
import pandas as pd


def filter_entity_connections(dataframe, entity_ip='192.168.1.1'):
    """
    Filter connections for a specific entity IP.
    Handles both conn log format (id.orig_h, id.resp_h) and ARP log format (orig_h, resp_h).
    
    Args:
        dataframe (pd.DataFrame): Input dataframe with connection data
        entity_ip (str): IP address to filter for
        
    Returns:
        pd.DataFrame: Filtered dataframe containing connections involving entity_ip
    """
    # Check if this is conn log format (id.orig_h, id.resp_h)
    if 'id.orig_h' in dataframe.columns and 'id.resp_h' in dataframe.columns:
        filtered_entity = dataframe[
            (dataframe['id.orig_h'] == entity_ip) | 
            (dataframe['id.resp_h'] == entity_ip)
        ]
    # Check if this is ARP log format (orig_h, resp_h)
    elif 'orig_h' in dataframe.columns and 'resp_h' in dataframe.columns:
        filtered_entity = dataframe[
            (dataframe['orig_h'] == entity_ip) | 
            (dataframe['resp_h'] == entity_ip)
        ]
    else:
        # No recognized format, return empty dataframe
        print(f"Warning: No recognized IP columns found in dataframe. Available columns: {dataframe.columns.tolist()}")
        filtered_entity = dataframe.iloc[0:0]  # Empty dataframe with same structure
        
    return filtered_entity


def resample_connections_by_time_unit(dataframe, time_unit='1s', count_type='total', entity_ip='192.168.1.1'):
    """
    Count connections per time unit for time series analysis
    
    Parameters:
    dataframe: Filtered connection DataFrame with 'ts' timestamp column
    time_unit: Time unit for resampling ('1s', '5s', '10s', '1min', etc.)
    count_type: Type of counting ('total', 'unique_src', 'unique_dst', 'unique_pairs')
    entity_ip: IP address of the monitored entity for direction calculation
    
    Returns:
    Tuple: (DataFrame with time series of connection counts, IP pairs mapping)
    """
    
    # Convert timestamp to datetime if not already
    if dataframe['ts'].dtype != 'datetime64[ns]':
        resampled_df = dataframe.copy()
        resampled_df['ts'] = pd.to_datetime(pd.to_numeric(resampled_df['ts']), unit='s')
    else:
        resampled_df = dataframe.copy()
        
    # Set timestamp as index for resampling
    resampled_df.set_index('ts', inplace=True)
    
    # Create IP pairs mapping for each timestamp
    ip_pairs_mapping = {}
    
    def extract_ip_pairs(group):
        """Extract IP pairs for a given time group"""
        pairs = []
        for _, row in group.iterrows():
            # Handle both conn log format (id.orig_h, id.resp_h) and ARP log format (orig_h, resp_h)
            if 'id.orig_h' in row and 'id.resp_h' in row:
                src_ip = row['id.orig_h']
                dst_ip = row['id.resp_h']
            elif 'orig_h' in row and 'resp_h' in row:
                src_ip = row['orig_h']
                dst_ip = row['resp_h']
            else:
                continue  # Skip if no recognized format
            
            # Determine direction based on entity_ip
            if src_ip == entity_ip:
                direction = "SEND"
                communicates_with = dst_ip
            else:
                direction = "RECEIVE"
                communicates_with = src_ip
                
            pairs.append({
                'IP': entity_ip,
                'communicateswith': communicates_with,
                'direction': direction,
                'original_timestamp': group.index[0]
            })
        return pairs
    
    # Count connections based on specified type and capture IP pairs
    if count_type == 'total':
        # Total number of connections per time unit
        connection_counts = resampled_df.resample(time_unit).size()
        column_name = 'total_connections'
        
    elif count_type == 'unique_src':
        # Number of unique source IPs per time unit
        if 'id.orig_h' in resampled_df.columns:
            connection_counts = resampled_df.resample(time_unit)['id.orig_h'].nunique()
        elif 'orig_h' in resampled_df.columns:
            connection_counts = resampled_df.resample(time_unit)['orig_h'].nunique()
        else:
            raise ValueError("No recognized source IP column found")
        column_name = 'unique_sources'
        
    elif count_type == 'unique_dst':
        # Number of unique destination IPs per time unit
        if 'id.resp_h' in resampled_df.columns:
            connection_counts = resampled_df.resample(time_unit)['id.resp_h'].nunique()
        elif 'resp_h' in resampled_df.columns:
            connection_counts = resampled_df.resample(time_unit)['resp_h'].nunique()
        else:
            raise ValueError("No recognized destination IP column found")
        column_name = 'unique_destinations'
        
    elif count_type == 'unique_pairs':
        # Number of unique source-destination pairs per time unit
        def count_unique_pairs(group):
            if 'id.orig_h' in group.columns and 'id.resp_h' in group.columns:
                return group[['id.orig_h', 'id.resp_h']].drop_duplicates().shape[0]
            elif 'orig_h' in group.columns and 'resp_h' in group.columns:
                return group[['orig_h', 'resp_h']].drop_duplicates().shape[0]
            else:
                return 0
        connection_counts = resampled_df.resample(time_unit).apply(count_unique_pairs)
        column_name = 'unique_pairs'
        
    else:
        raise ValueError(f"Unknown count_type: {count_type}")
    
    # Extract IP pairs for each time interval
    for time_interval, group in resampled_df.resample(time_unit):
        if not group.empty:
            pairs = extract_ip_pairs(group)
            ip_pairs_mapping[time_interval] = pairs
    
    # Convert to DataFrame
    result_df = connection_counts.to_frame(name=column_name)
    
    return result_df, ip_pairs_mapping


def apply_rolling_mean(df, window_size=5):
    """
    Apply rolling window statistics for smoothing and feature extraction
    
    Parameters:
    df: DataFrame with connection counts
    window_size: Size of the rolling window
    
    
    Returns:
    DataFrame with original data plus rolling statistics
    """
    df = df.copy()
    column_name = df.columns[0]  # Get the main column name
    

    df[f'rolling_mean'] = df[column_name].rolling(window=window_size).mean()
    
    # Fill NaN values with backward fill for initial values
    df[f'rolling_mean'].bfill(inplace=True)
    
    return df


def conn_log_preprocessing_pipeline(conn_cut_dataframe):
    """
    Execute the connection log preprocessing pipeline
    
    Parameters:
    conn_cut_dataframe: Raw connection log DataFrame
    
    Returns:
    Processed DataFrame with rolling statistics
    """
    
    # Step 1: Filter connections for specific entity (PLC1)
    entity_ip = '192.168.1.1'  # PLC1 IP address
    filtered_connections = filter_entity_connections(conn_cut_dataframe, entity_ip)

    # Step 2: Resample connections by time unit (1 second intervals)
    time_unit = '1s'
    count_type = 'unique_pairs'  # Options: 'total', 'unique_src', 'unique_dst', 'unique_pairs'

    resampled_data, ip_pairs_mapping = resample_connections_by_time_unit(
        filtered_connections, 
        time_unit=time_unit, 
        count_type=count_type,
        entity_ip=entity_ip
    )

    # Step 3: Apply rolling statistics for smoothing
    window_size = 5  
    rolling_stats = ['mean']  # Calculate rolling mean and standard deviation

    processed_data = apply_rolling_mean(
        resampled_data, 
        window_size=window_size, 
    )

    processed_data.to_csv("processed_data_normal.csv", index=True)
    return processed_data


def write_alert(alert: dict, alerts_collection_func, net_alerts_json_file, first_alert_flag):
    """
    Write alert to both MongoDB and JSON file
    
    Parameters:
    alert: Dictionary containing alert information
    alerts_collection_func: Function to get MongoDB alerts collection
    net_alerts_json_file: Path to JSON alerts file
    first_alert_flag: Boolean flag tracking if this is the first alert
    
    Returns:
    Updated first_alert_flag
    """
    try:
        # Get MongoDB collection using the module
        alerts_collection = alerts_collection_func()
        if alerts_collection is not None:
            alerts_collection.insert_one(alert)
        else:
            print("WARNING: MongoDB connection not available for alert storage")
    except Exception as e:
        print(f"WARNING: failed to write alert to MongoDB: {e}")
    
    try:
        with open(net_alerts_json_file, 'a') as jf:
            if not first_alert_flag:
                jf.write(',\n')
            jf.write(json.dumps(alert, default=str))
            first_alert_flag = False
    except Exception as e:
        print(f"WARNING: failed to write alert to JSON file: {e}")
    
    return first_alert_flag
