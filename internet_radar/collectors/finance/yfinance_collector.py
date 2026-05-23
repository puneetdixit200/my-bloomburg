from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="Yahoo Finance", category="finance", topic="stock trends", score=60)
