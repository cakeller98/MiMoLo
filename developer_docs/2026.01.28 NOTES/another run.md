Main POWERSHELL command and output:

``` powershell
powershell -ExecutionPolicy ByPass -File "v:\CODE\MiMoLo\start_monitor.ps1"
```

``` output
powershell -ExecutionPolicy ByPass -File "v:\CODE\MiMoLo\start_monitor.ps1"
Platform check: Windows 10+ with Unix socket support
Configuration loaded from: mimolo.toml
Spawned Field-Agent: agent_template
MiMoLo starting...
Cooldown: 600.0s
Poll tick: 200.0ms
Field-Agents: 1

Sent flush to agent_template
[19:28:17] INFO     [ERR] +- \U0001f680 Field-Agent Starting -+
           DEBUG     RECV: {"type": "handshake", "timestamp": "2026-01-29T03:28:17.678399+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "min_app_version": "0.3.0",       
                    "capabilities": ["summary", "heartbeat", "status", "error"], "data": {}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.679198+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "=== \ud83d\udce4   
                    Sent: handshake ===\n{\"type\": \"handshake\", \"timestamp\": \"2026-01-29T03:28:17.678399+00:00\", \"agent_id\":       
                    \"template_agent-001\", \"agent_label\": \"template_agent\", \"protocol_version\": \"0.3\", \"agent_version\":
                    \"1.0.0\", \"min_app_version\": \"0.3.0\", \"capabilities\": [\"summary\", \"heartbeat\", \"status\", \"error\"],       
                    \"data\": {}}", "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.680226+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83c\udfa7       
                    Command listener thread started", "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.680514+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "=== \ud83d\udce5   
                    Received command: flush ===\n{\n  \"cmd\": \"flush\",\n  \"args\": {},\n  \"id\": null,\n  \"sequence\": null\n}",      
                    "markup": true, "data": {}, "extra": {}}
           INFO     [ERR] | template_agent            |
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.680615+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\u2699\ufe0f       
                    Worker thread started", "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.680845+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcbe FLUSH 
                    command received - taking snapshot", "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.680886+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcf8       
                    Snapshot taken: 0 items from 2026-01-29T03:28:17.680826+00:00 to 2026-01-29T03:28:17.680826+00:00", "markup": true,     
                    "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "ack", "timestamp": "2026-01-29T03:28:17.680826+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "ack_command": "flush", "message": "Flushed 0    
                    samples", "data": {}, "metrics": {"flushed_count": 0, "queue": 1}}
           INFO     [ERR] | ID: template_agent-001    |
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.680982+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "=== \ud83d\udce4   
                    Sent: ack ===\n{\"type\": \"ack\", \"timestamp\": \"2026-01-29T03:28:17.680826+00:00\", \"agent_id\":
                    \"template_agent-001\", \"agent_label\": \"template_agent\", \"protocol_version\": \"0.3\", \"agent_version\":
                    \"1.0.0\", \"ack_command\": \"flush\", \"message\": \"Flushed 0 samples\", \"data\": {}, \"metrics\":
                    {\"flushed_count\": 0, \"queue\": 1}}", "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.681094+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udce6       
                    Summarizer thread started", "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.681151+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83c\udfaf All   
                    threads started", "markup": true, "data": {}, "extra": {}}
           INFO     [ERR] | Version: 1.0.0            |
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.681216+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udd04       
                    Summarizing 0 items...", "markup": true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "summary", "timestamp": "2026-01-29T03:28:17.680826+00:00", "agent_id": "template_agent-001",
                    "agent_label": "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "data": {"start":
                    "2026-01-29T03:28:17.680826+00:00", "end": "2026-01-29T03:28:17.680826+00:00", "duration_s": 0.0, "sample_count": 0,    
                    "samples": []}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:17.682303+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "=== \ud83d\udce4   
                    Sent: summary ===\n{\"type\": \"summary\", \"timestamp\": \"2026-01-29T03:28:17.680826+00:00\", \"agent_id\":
                    \"template_agent-001\", \"agent_label\": \"template_agent\", \"protocol_version\": \"0.3\", \"agent_version\":
                    \"1.0.0\", \"data\": {\"start\": \"2026-01-29T03:28:17.680826+00:00\", \"end\": \"2026-01-29T03:28:17.680826+00:00\",
                    \"duration_s\": 0.0, \"sample_count\": 0, \"samples\": []}}", "markup": true, "data": {}, "extra": {}}
           INFO     [ERR] | Protocol: 0.3             |
           INFO     [ERR] | Sample Interval: 5.0s     |
           INFO     [ERR] | Heartbeat Interval: 15.0s |
           INFO     [ERR] +---------------------------+
 === 📤 Sent: handshake ===
 {"type": "handshake", "timestamp": "2026-01-29T03:28:17.678399+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",
"protocol_version": "0.3", "agent_version": "1.0.0", "min_app_version": "0.3.0", "capabilities": ["summary", "heartbeat", "status",
"error"], "data": {}}
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
 📸 Snapshot taken: 0 items from 2026-01-29T03:28:17.680826+00:00 to 2026-01-29T03:28:17.680826+00:00
 === 📤 Sent: ack ===
 {"type": "ack", "timestamp": "2026-01-29T03:28:17.680826+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",
"protocol_version": "0.3", "agent_version": "1.0.0", "ack_command": "flush", "message": "Flushed 0 samples", "data": {}, "metrics":
{"flushed_count": 0, "queue": 1}}
 📦 Summarizer thread started
 🎯 All threads started
 🔄 Summarizing 0 items...
           INFO     [EVENT] 03:28:17 | template_agent.summary | Data: {'start': '2026-01-29T03:28:17.680826+00:00', 'end':
                    '2026-01-29T03:28:17.680826+00:00', 'duration_s': 0.0, 'sample_count': 0, 'samples': []}
 === 📤 Sent: summary ===
 {"type": "summary", "timestamp": "2026-01-29T03:28:17.680826+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",
"protocol_version": "0.3", "agent_version": "1.0.0", "data": {"start": "2026-01-29T03:28:17.680826+00:00", "end":
"2026-01-29T03:28:17.680826+00:00", "duration_s": 0.0, "sample_count": 0, "samples": []}}
[19:28:22] DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:22.701957+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca Sample
                    #1 accumulated (total: 1)", "markup": true, "data": {}, "extra": {}}
 📊 Sample #1 accumulated (total: 1)
[19:28:27] DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:27.722593+00:00", "agent_id": "template_agent-001", "agent_label":
                    "template_agent", "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca Sample
                    #2 accumulated (total: 2)", "markup": true, "data": {}, "extra": {}}
 📊 Sample #2 accumulated (total: 2)
[19:28:32] DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:32.742581+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca Sample #3 accumulated (total: 3)", "markup":    
                    true, "data": {}, "extra": {}}
           DEBUG     RECV: {"type": "heartbeat", "timestamp": "2026-01-29T03:28:32.742526+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",
                    "protocol_version": "0.3", "agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0, "accumulated_count": 3, "sample_count": 3}}
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:32.742825+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "=== \ud83d\udce4 Sent: heartbeat ===\n{\"type\":
                    \"heartbeat\", \"timestamp\": \"2026-01-29T03:28:32.742526+00:00\", \"agent_id\": \"template_agent-001\", \"agent_label\": \"template_agent\",  
                    \"protocol_version\": \"0.3\", \"agent_version\": \"1.0.0\", \"data\": {}, \"metrics\": {\"queue\": 0, \"accumulated_count\": 3,
                    \"sample_count\": 3}}", "markup": true, "data": {}, "extra": {}}
 📊 Sample #3 accumulated (total: 3)
❤️  agent_template | {'queue': 0, 'accumulated_count': 3, 'sample_count': 3}
 === 📤 Sent: heartbeat ===
 {"type": "heartbeat", "timestamp": "2026-01-29T03:28:32.742526+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent", "protocol_version":      
"0.3", "agent_version": "1.0.0", "data": {}, "metrics": {"queue": 0, "accumulated_count": 3, "sample_count": 3}}
[19:28:37] DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:37.762428+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca Sample #4 accumulated (total: 4)", "markup":    
                    true, "data": {}, "extra": {}}
 📊 Sample #4 accumulated (total: 4)
[19:28:42] DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:42.784460+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\udcca Sample #5 accumulated (total: 5)", "markup":    
                    true, "data": {}, "extra": {}}
 📊 Sample #5 accumulated (total: 5)
[19:28:44] DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:44.823163+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\u26a0\ufe0f  KeyboardInterrupt - shutting down", "markup":  
                    true, "data": {}, "extra": {}}

Shutting down...
           INFO     [ERR] +-----------------------+
Shutting down...
           INFO     [EVENT] 03:28:44 | orchestrator.shutdown_initiated | Data: {'agent_count': 1, 'expected_shutdown_messages': 2, 'note': 'Following entries are   
                    agent shutdown/flush messages'}
Sending shutdown sequence to Field-Agents...
Sent shutdown SEQUENCE to agent_template
           INFO     [ERR] | Agent stopped cleanly |
 ⚠️  KeyboardInterrupt - shutting down
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:44.830122+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "=== \ud83d\udce5 Received command: sequence ===\n{\n
                    \"cmd\": \"sequence\",\n  \"args\": {},\n  \"id\": null,\n  \"sequence\": [\n    \"stop\",\n    \"flush\",\n    \"shutdown\"\n  ]\n}", "markup":
                    true, "data": {}, "extra": {}}
 === 📥 Received command: sequence ===
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:44.830202+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\uded1 Command listener shutting down", "markup": true,
                    "data": {}, "extra": {}}
 {
           INFO     [ERR] +-----------------------+
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
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:44.894483+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\uded1 Worker thread shutting down", "markup": true,   
                    "data": {}, "extra": {}}
 🛑 Worker thread shutting down
           DEBUG     RECV: {"type": "log", "timestamp": "2026-01-29T03:28:44.949508+00:00", "agent_id": "template_agent-001", "agent_label": "template_agent",      
                    "protocol_version": "0.3", "agent_version": "1.0.0", "level": "debug", "message": "\ud83d\uded1 Summarizer thread shutting down", "markup":     
                    true, "data": {}, "extra": {}}
 🛑 Summarizer thread shutting down
Agent agent_template did not ACK STOP (timeout)
Agent agent_template did not send summary after FLUSH (timeout)
Waiting for Field-Agent processes to exit...
[19:28:48] INFO     [EVENT] 03:28:48 | orchestrator.shutdown_complete | Data: {'agent_count_final': 0, 'timestamp': '2026-01-29T03:28:48.865607+00:00', 'note': 'All
                    agents shutdown and sinks closed', 'summaries_written_during_shutdown': 0, 'logs_written_during_shutdown': 5, 'acks_received_during_shutdown':  
                    0}
MiMoLo stopped.
Shutdown complete.
```

spawned process output in separate powershell window:
```
# MiMoLo Agent Log: agent_template
# Started at 2026-01-29T03:28:15.976417+00:00

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

the jsonl log file generated is at (after renaming):
logs\2026-01-29yy.mimolo.jsonl