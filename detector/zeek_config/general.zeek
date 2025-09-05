@load icsnpp/enip
event zeek_init()
    {
    
    Log::disable_stream(DHCP::LOG);
    Log::disable_stream(Files::LOG);
    Log::disable_stream(NTP::LOG);
    Log::disable_stream(SSL::LOG);
    Log::disable_stream(X509::LOG);
    Log::disable_stream(DCE_RPC::LOG);
    Log::disable_stream(NTLM::LOG);
    Log::disable_stream(PacketFilter::LOG);
    Log::disable_stream(ENIP::LOG_CIP_IO);
    }
#redef Log::default_rotation_interval = 120secs;