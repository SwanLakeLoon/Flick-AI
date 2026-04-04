#!/usr/bin/env python3
"""
Flick AI — Pipeline Report Generator
====================================
Automatically parses the latest or specified batch report and prints
the summary metrics so you don't need to ask the agent to do it.
"""

import os
import sys
import glob
import json

# Add src to path so we can import the existing output formatter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from pipeline.output import print_stats_summary

def get_latest_stats_file(base_dir="videos") -> str:
    """Finds the most recently modified *_stats.json file."""
    search_pattern = os.path.join(base_dir, "**", "*_stats.json")
    files = glob.glob(search_pattern, recursive=True)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def main():
    target_file = None
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.endswith("_stats.json"):
            target_file = arg
        elif os.path.isdir(arg):
            # Find stats in that directory
            files = glob.glob(os.path.join(arg, "*_stats.json"))
            if files:
                target_file = max(files, key=os.path.getmtime)
    else:
        target_file = get_latest_stats_file()

    if not target_file or not os.path.exists(target_file):
        print(f"No stats.json file found. Have you run the pipeline yet?")
        sys.exit(1)

    print(f"Loading stats from: {target_file}")
    with open(target_file, "r") as f:
        try:
            stats = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Could not parse {target_file} as JSON.")
            sys.exit(1)

    print_stats_summary(stats)

if __name__ == "__main__":
    main()
