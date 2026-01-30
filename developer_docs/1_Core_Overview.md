## Core Overview

MiMoLo is a modular monitoring and logging framework built around ultra-lightweight, autonomous Agents (formerly “Agents”). Each agent performs an independent sensing task—whatever that may be—while consuming only a microscopic share of system resources. Agents accumulate and condense their sampled data into meaningful summaries rather than raw streams, reporting back to the orchestrator only when the information is significant or time-bounded. They self-monitor their health, communicate asynchronously through resilient JSON channels, and can dynamically throttle themselves or be throttled by the orchestrator. This cooperative design enables thousands of concurrent agents to operate efficiently, providing continuous insight without measurable impact on system performance.

### ...next [[2_Core_Concepts]]
