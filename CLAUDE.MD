# Agent Sandbox - Mission Statement

## Overview

This repository is an experimental sandbox for exploring agent architectures that diverge from traditional on-premise execution models.

## Core Focus

Investigating agents that:
- Run as long-lived processes in remote environments (e.g., Kubernetes clusters)
- Operate independently from the user's local machine
- Have their own distinct identity while acting on behalf of users
- Function under delegated permissions granted by users

## Key Problem Space

**Identity and Authorization**: How do we architect agents that maintain their own identity while operating with user-delegated permissions? This explores the intersection of:
- Agent autonomy and persistence
- User authorization and trust boundaries
- Distributed system architectures
- Permission delegation models

## Repository Structure

This repository may contain multiple sub-projects as we explore different approaches and architectures within this problem space.

## Goals

- Experiment with different agent deployment models
- Explore permission delegation patterns
- Understand the operational characteristics of long-lived agent processes
- Investigate the security and trust implications of delegated agent authority
