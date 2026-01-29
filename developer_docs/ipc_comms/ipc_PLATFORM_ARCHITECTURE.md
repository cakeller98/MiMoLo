# mimolo/docs/PLATFORM_SUPPORT.md

# MiMoLo Platform Requirements

## Supported Platforms

### Windows
- ✅ **Windows 10 version 1803 or later** (April 2018+)
- ✅ **Windows 11** (all versions)
- ❌ Windows 7, 8, 8.1 (deprecated)
- ❌ Windows 10 older than version 1803 (deprecated)

**Why:** MiMoLo requires Unix domain socket support (AF_UNIX), which was added in Windows 10 build 17063.

**Check your version:**
```cmd
winver
```
Look for "Version 1803" or higher.

### macOS
- ✅ **macOS 10.13 High Sierra or later**
- ❌ macOS 10.12 Sierra or older (deprecated)

### Linux
- ✅ **Any modern distribution** (kernel 2.6+)
- ✅ Ubuntu 16.04+, Debian 8+, CentOS 7+, etc.

## Why These Requirements?

MiMoLo uses **Unix domain sockets** for inter-process communication because:
- **100x faster** than TCP (even on localhost)
- **Zero network exposure** (filesystem-only)
- **Scales to 500+ concurrent agents** without performance degradation
- **Cross-platform** on modern operating systems

Older platforms lack native Unix socket support and would require TCP fallback, which violates MiMoLo's performance requirements (<0.01% CPU per plugin).

## Migration Path for Unsupported Platforms

If you're on Windows 7/8 or old macOS:
1. **Upgrade your OS** (recommended)
2. **SLOWPOKE fallback** (not recommended, severe performance impact)

We do not provide TCP fallback because it would compromise the core design principle of minimal system impact.

# MiMoLo IPC Architecture and Platform Requirements

Agent ↔ Orchestrator: Agent JLP (stdin/stdout subprocess pipes)
  - Zero overhead
  - Scales to 1000s of agents
  - Already implemented

Dashboard ↔ Orchestrator: Unix domain sockets (2 sockets for bidirectional)
  - ~0.1ms latency
  - Minimal CPU
  - Same code on Windows 10+/macOS/Linux

Dashboard ↔ Report Plugin: Unix domain sockets
  - Consistent API
  - Fast progress updates
  - Isolated from orchestrator

Platform Requirements:
  ✅ Windows 10 version 1803+ (April 2018)
  ✅ macOS 10.13+ (High Sierra, 2017)
  ✅ Linux (any modern distro)
  
  ❌ NO TCP fallback
  ❌ NO support for old platforms*

* If you need to support legacy platforms (e.g., Windows 7/8, old macOS), see the SLOWPOKE module as a last-resort fallback option. It will function but with significant performance degradation and limitations.

