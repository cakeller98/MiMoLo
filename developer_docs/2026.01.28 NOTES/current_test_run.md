Main POWERSHELL command and output:

``` powershell
powershell -ExecutionPolicy ByPass -File "v:\CODE\MiMoLo\start_monitor.ps1"
```

``` output
Platform check: Windows 10+ with Unix socket support
Configuration loaded from: mimolo.toml
Spawned Field-Agent: agent_template
MiMoLo starting...
Cooldown: 600.0s
Poll tick: 200.0ms
Field-Agents: 1

Sent flush to agent_template
[19:09:48] INFO     [ERR] +- \U0001f680 Field-Agent Starting -+
           DEBUG     RECV: {"type": "handshake", "timestamp":
                    "2026-01-29T03:09:48.013368+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "min_app_version": "0.3.0", "capabilities":
                    ["summary", "heartbeat", "status", "error"], "data": {}}
           INFO     [ERR] | template_agent            |
           INFO     [ERR] | ID: template_agent-001    |
           INFO     [ERR] | Version: 1.0.0            |
           INFO     [ERR] | Protocol: 0.3             |
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.022725+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce4 Sent: handshake ===\n{\"type\": \"handshake\",
                    \"timestamp\": \"2026-01-29T03:09:48.013368+00:00\", \"agent_id\":   
                    \"template_agent-001\", \"agent_label\": \"template_agent\",
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\",
                    \"min_app_version\": \"0.3.0\", \"capabilities\": [\"summary\",      
                    \"heartbeat\", \"status\", \"error\"], \"data\": {}}", "markup":     
                    true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.023678+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83c\udfa7 
                    Command listener thread started", "markup": true, "data": {},        
                    "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.023959+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce5 Received command: flush ===\n{\n  \"cmd\": \"flush\",\n 
                    \"args\": {},\n  \"id\": null,\n  \"sequence\": null\n}", "markup":  
                    true, "data": {}, "extra": {}}
           INFO     [ERR] | Sample Interval: 5.0s     |
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024046+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\u2699\ufe0f 
                    Worker thread started", "markup": true, "data": {}, "extra": {}}     
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024256+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcbe 
                    FLUSH command received - taking snapshot", "markup": true, "data":   
                    {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024292+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcf8 
                    Snapshot taken: 0 items from 2026-01-29T03:09:48.024239+00:00 to     
                    2026-01-29T03:09:48.024239+00:00", "markup": true, "data": {},       
                    "extra": {}}
           DEBUG     RECV: {"type": "ack", "timestamp":
                    "2026-01-29T03:09:48.024239+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "ack_command": "flush", "message": "Flushed
                    0 samples", "data": {}, "metrics": {"flushed_count": 0, "queue": 1}} 
           INFO     [ERR] | Heartbeat Interval: 15.0s |
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024372+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce4 Sent: ack ===\n{\"type\": \"ack\", \"timestamp\":       
                    \"2026-01-29T03:09:48.024239+00:00\", \"agent_id\":
                    \"template_agent-001\", \"agent_label\": \"template_agent\",
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\",
                    \"ack_command\": \"flush\", \"message\": \"Flushed 0 samples\",      
                    \"data\": {}, \"metrics\": {\"flushed_count\": 0, \"queue\": 1}}",   
                    "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024487+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udce6 
                    Summarizer thread started", "markup": true, "data": {}, "extra": {}} 
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024544+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83c\udfaf 
                    All threads started", "markup": true, "data": {}, "extra": {}}       
           INFO     [ERR] +---------------------------+
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024613+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udd04 
                    Summarizing 0 items...", "markup": true, "data": {}, "extra": {}}    
           DEBUG     RECV: {"type": "summary", "timestamp":
                    "2026-01-29T03:09:48.024239+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "data": {"start":
                    "2026-01-29T03:09:48.024239+00:00", "end":
                    "2026-01-29T03:09:48.024239+00:00", "duration_s": 0.0,
                    "sample_count": 0, "samples": []}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:48.024776+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce4 Sent: summary ===\n{\"type\": \"summary\",
                    \"timestamp\": \"2026-01-29T03:09:48.024239+00:00\", \"agent_id\":   
                    \"template_agent-001\", \"agent_label\": \"template_agent\",
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\",
                    \"data\": {\"start\": \"2026-01-29T03:09:48.024239+00:00\", \"end\": 
                    \"2026-01-29T03:09:48.024239+00:00\", \"duration_s\": 0.0,
                    \"sample_count\": 0, \"samples\": []}}", "markup": true, "data": {}, 
                    "extra": {}}
 === 📤 Sent: handshake ===
 {"type": "handshake", "timestamp": "2026-01-29T03:09:48.013368+00:00", "agent_id": 
"template_agent-001", "agent_label": "template_agent", "protocol_version": "0.3",        
"agent_version": "1.0.0", "min_app_version": "0.3.0", "capabilities": ["summary",        
"heartbeat", "status", "error"], "data": {}}
 🎧 Command listener thread started
 === 📥 Received command: flush ===
 {
   "cmd": "flush",
   "args": {},
   "id": null,
   "sequence": null
 }
 ⚙️  Worker thread started
 💾 FLUSH command received - taking snapshot
 📸 Snapshot taken: 0 items from 2026-01-29T03:09:48.024239+00:00 to
2026-01-29T03:09:48.024239+00:00
 === 📤 Sent: ack ===
 {"type": "ack", "timestamp": "2026-01-29T03:09:48.024239+00:00", "agent_id":
"template_agent-001", "agent_label": "template_agent", "protocol_version": "0.3",        
"agent_version": "1.0.0", "ack_command": "flush", "message": "Flushed 0 samples", "data":
{}, "metrics": {"flushed_count": 0, "queue": 1}}
 📦 Summarizer thread started
 🎯 All threads started
 🔄 Summarizing 0 items...
           INFO     [EVENT] 03:09:48 | template_agent.summary | Data: {'start':
                    '2026-01-29T03:09:48.024239+00:00', 'end':
                    '2026-01-29T03:09:48.024239+00:00', 'duration_s': 0.0,
                    'sample_count': 0, 'samples': []}
 === 📤 Sent: summary ===
 {"type": "summary", "timestamp": "2026-01-29T03:09:48.024239+00:00", "agent_id":        
"template_agent-001", "agent_label": "template_agent", "protocol_version": "0.3",        
"agent_version": "1.0.0", "data": {"start": "2026-01-29T03:09:48.024239+00:00", "end":   
"2026-01-29T03:09:48.024239+00:00", "duration_s": 0.0, "sample_count": 0, "samples": []}}
[19:09:53] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:53.046111+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #1 accumulated (total: 1)", "markup": true, "data": {},       
                    "extra": {}}
 📊 Sample #1 accumulated (total: 1)
[19:09:58] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:09:58.067543+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #2 accumulated (total: 2)", "markup": true, "data": {},       
                    "extra": {}}
 📊 Sample #2 accumulated (total: 2)
[19:10:03] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:03.088254+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #3 accumulated (total: 3)", "markup": true, "data": {},       
                    "extra": {}}
           DEBUG     RECV: {"type": "heartbeat", "timestamp":
                    "2026-01-29T03:10:03.088221+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0,        
                    "accumulated_count": 3, "sample_count": 3}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:03.088415+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce4 Sent: heartbeat ===\n{\"type\": \"heartbeat\",
                    \"timestamp\": \"2026-01-29T03:10:03.088221+00:00\", \"agent_id\":   
                    \"template_agent-001\", \"agent_label\": \"template_agent\",
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\",
                    \"data\": {}, \"metrics\": {\"queue\": 0, \"accumulated_count\": 3,  
                    \"sample_count\": 3}}", "markup": true, "data": {}, "extra": {}}     
 📊 Sample #3 accumulated (total: 3)
❤️  agent_template | {'queue': 0, 'accumulated_count': 3, 'sample_count': 3}
 === 📤 Sent: heartbeat ===
 {"type": "heartbeat", "timestamp": "2026-01-29T03:10:03.088221+00:00", "agent_id":      
"template_agent-001", "agent_label": "template_agent", "protocol_version": "0.3",        
"agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0, "accumulated_count": 3,    
"sample_count": 3}}
[19:10:08] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:08.109131+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #4 accumulated (total: 4)", "markup": true, "data": {},       
                    "extra": {}}
 📊 Sample #4 accumulated (total: 4)
[19:10:13] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:13.132489+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #5 accumulated (total: 5)", "markup": true, "data": {},       
                    "extra": {}}
 📊 Sample #5 accumulated (total: 5)
[19:10:18] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:18.154442+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #6 accumulated (total: 6)", "markup": true, "data": {},       
                    "extra": {}}
           DEBUG     RECV: {"type": "heartbeat", "timestamp":
                    "2026-01-29T03:10:18.154406+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0,        
                    "accumulated_count": 6, "sample_count": 6}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:18.154600+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce4 Sent: heartbeat ===\n{\"type\": \"heartbeat\",
                    \"timestamp\": \"2026-01-29T03:10:18.154406+00:00\", \"agent_id\":   
                    \"template_agent-001\", \"agent_label\": \"template_agent\",
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\",
                    \"data\": {}, \"metrics\": {\"queue\": 0, \"accumulated_count\": 6,  
                    \"sample_count\": 6}}", "markup": true, "data": {}, "extra": {}}     
 📊 Sample #6 accumulated (total: 6)
❤️  agent_template | {'queue': 0, 'accumulated_count': 6, 'sample_count': 6}
 === 📤 Sent: heartbeat ===
 {"type": "heartbeat", "timestamp": "2026-01-29T03:10:18.154406+00:00", "agent_id":      
"template_agent-001", "agent_label": "template_agent", "protocol_version": "0.3",        
"agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0, "accumulated_count": 6,    
"sample_count": 6}}
[19:10:23] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:23.175301+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #7 accumulated (total: 7)", "markup": true, "data": {},       
                    "extra": {}}
 📊 Sample #7 accumulated (total: 7)
[19:10:28] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:28.196894+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #8 accumulated (total: 8)", "markup": true, "data": {},       
                    "extra": {}}
 📊 Sample #8 accumulated (total: 8)
[19:10:33] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:33.218297+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #9 accumulated (total: 9)", "markup": true, "data": {},       
                    "extra": {}}
           DEBUG     RECV: {"type": "heartbeat", "timestamp":
                    "2026-01-29T03:10:33.218244+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0,        
                    "accumulated_count": 9, "sample_count": 9}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:33.218540+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce4 Sent: heartbeat ===\n{\"type\": \"heartbeat\",
                    \"timestamp\": \"2026-01-29T03:10:33.218244+00:00\", \"agent_id\":   
                    \"template_agent-001\", \"agent_label\": \"template_agent\",
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\",
                    \"data\": {}, \"metrics\": {\"queue\": 0, \"accumulated_count\": 9,  
                    \"sample_count\": 9}}", "markup": true, "data": {}, "extra": {}}     
 📊 Sample #9 accumulated (total: 9)
❤️  agent_template | {'queue': 0, 'accumulated_count': 9, 'sample_count': 9}
 === 📤 Sent: heartbeat ===
 {"type": "heartbeat", "timestamp": "2026-01-29T03:10:33.218244+00:00", "agent_id":      
"template_agent-001", "agent_label": "template_agent", "protocol_version": "0.3",        
"agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0, "accumulated_count": 9,    
"sample_count": 9}}
[19:10:38] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:38.240038+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #10 accumulated (total: 10)", "markup": true, "data": {},     
                    "extra": {}}
 📊 Sample #10 accumulated (total: 10)
[19:10:43] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:43.260668+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #11 accumulated (total: 11)", "markup": true, "data": {},     
                    "extra": {}}
 📊 Sample #11 accumulated (total: 11)
[19:10:48] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:48.281876+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #12 accumulated (total: 12)", "markup": true, "data": {},     
                    "extra": {}}
           DEBUG     RECV: {"type": "heartbeat", "timestamp":
                    "2026-01-29T03:10:48.281841+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0,        
                    "accumulated_count": 12, "sample_count": 12}}
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:48.282046+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce4 Sent: heartbeat ===\n{\"type\": \"heartbeat\",
                    \"timestamp\": \"2026-01-29T03:10:48.281841+00:00\", \"agent_id\":   
                    \"template_agent-001\", \"agent_label\": \"template_agent\",
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\",
                    \"data\": {}, \"metrics\": {\"queue\": 0, \"accumulated_count\": 12, 
                    \"sample_count\": 12}}", "markup": true, "data": {}, "extra": {}}    
 📊 Sample #12 accumulated (total: 12)
❤️  agent_template | {'queue': 0, 'accumulated_count': 12, 'sample_count': 12}
 === 📤 Sent: heartbeat ===
 {"type": "heartbeat", "timestamp": "2026-01-29T03:10:48.281841+00:00", "agent_id":      
"template_agent-001", "agent_label": "template_agent", "protocol_version": "0.3",        
"agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0, "accumulated_count": 12,   
"sample_count": 12}}
[19:10:53] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:53.302430+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #13 accumulated (total: 13)", "markup": true, "data": {},     
                    "extra": {}}
 📊 Sample #13 accumulated (total: 13)
[19:10:58] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:10:58.322465+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca 
                    Sample #14 accumulated (total: 14)", "markup": true, "data": {},     
                    "extra": {}}
 📊 Sample #14 accumulated (total: 14)
[19:11:00] DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:11:00.199959+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\u26a0\ufe0f 
                    KeyboardInterrupt - shutting down", "markup": true, "data": {},      
                    "extra": {}}

Shutting down...
           INFO     [ERR] +-----------------------+
Shutting down...
           INFO     [EVENT] 03:11:00 | orchestrator.shutdown_initiated | Data:
                    {'agent_count': 1, 'expected_shutdown_messages': 2, 'note':
                    'Following entries are agent shutdown/flush messages'}
Sending shutdown sequence to Field-Agents...
           INFO     [ERR] | Agent stopped cleanly |
Sent shutdown SEQUENCE to agent_template
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:11:00.206349+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "===
                    \ud83d\udce5 Received command: sequence ===\n{\n  \"cmd\":
                    \"sequence\",\n  \"args\": {},\n  \"id\": null,\n  \"sequence\": [\n 
                    \"stop\",\n    \"flush\",\n    \"shutdown\"\n  ]\n}", "markup": true,
                    "data": {}, "extra": {}}
 ⚠️  KeyboardInterrupt - shutting down
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:11:00.206428+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\uded1 
                    Command listener shutting down", "markup": true, "data": {}, "extra":
                    {}}
 === 📥 Received command: sequence ===
           INFO     [ERR] +-----------------------+
 {
   "cmd": "sequence",
   "args": {},
   "id": null,
   "sequence": [
     "stop",
     "flush",
     "shutdown"
   ]
 }
 🛑 Command listener shutting down
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:11:00.229287+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\uded1 
                    Worker thread shutting down", "markup": true, "data": {}, "extra":   
                    {}}
 🛑 Worker thread shutting down
           DEBUG     RECV: {"type": "log", "timestamp":
                    "2026-01-29T03:11:00.673455+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3",
                    "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\uded1 
                    Summarizer thread shutting down", "markup": true, "data": {},        
                    "extra": {}}
 🛑 Summarizer thread shutting down
Agent agent_template did not ACK STOP (timeout)
Agent agent_template did not send summary after FLUSH (timeout)
Waiting for Field-Agent processes to exit...
[19:11:04] INFO     [EVENT] 03:11:04 | orchestrator.shutdown_complete | Data:
                    {'agent_count_final': 0, 'timestamp':
                    '2026-01-29T03:11:04.236317+00:00', 'note': 'All agents shutdown and 
                    sinks closed', 'summaries_written_during_shutdown': 0,
                    'logs_written_during_shutdown': 5, 'acks_received_during_shutdown':  
                    0}
MiMoLo stopped.
Shutdown complete.
```

spawned process output in separate powershell window:
```
# Started at 2026-01-29T03:09:46.290914+00:00

+- \U0001f680 Field-Agent Starting -+
| template_agent            |
| ID: template_agent-001    |
| Version: 1.0.0            |
| Protocol: 0.3             |
| Sample Interval: 5.0s     |
| Heartbeat Interval: 15.0s |
+---------------------------+
+-----------------------+
| Agent stopped cleanly |
+-----------------------+
```

the jsonl log file generated is at:
logs\2026-01-29xx.mimolo.jsonl