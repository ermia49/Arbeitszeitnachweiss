#!/usr/bin/env python3

"""
Create sample data for the Arbeitszeitnachweise Generator

This script generates sample CSV files for testing the application:
1. Fahrtenbuch (driving log) with random ride data
2. Fahrerübersicht (driver overview) with sample drivers

Usage:
    python create_sample_data.py [--month YYYY-MM] [--drivers NUM] [--rides NUM]
"""

import os
import sys
import csv
import random
import argparse
from datetime import datetime, timedelta, time

# Sample driver names
DRIVERS = [
    "Max Mustermann",
    "Anna Schmidt",
    "Felix Weber",
    "Lisa Müller",
    "Thomas Becker",
    "Sarah Koch",
    "Michael Wagner",
    "Julia Hoffmann",
    "David Schneider",
    "Laura Meyer"
]

def random_time(start_hour=5, end_hour=22):
    """Generate a random time between start_hour and end_hour"""
    hour = random.randint(start_hour, end_hour)
    minute = random.choice([0, 15, 30, 45])
    return time(hour, minute)

def generate_time_pair():
    """Generate a start and end time for a ride"""
    start_time = random_time(5, 20)
    
    # Generate ride duration between 15 minutes and 3 hours
    duration_minutes = random.randint(15, 180)
    
    # Calculate end time
    start_dt = datetime.combine(datetime.today(), start_time)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    end_time = end_dt.time()
    
    return start_time, end_time

def create_fahrtenbuch(filename, month, num_drivers, num_rides):
    """Create a sample Fahrtenbuch (driving log) CSV file"""
    # Parse month string to datetime
    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m")
        except ValueError:
            print("Invalid month format. Use YYYY-MM")
            sys.exit(1)
    else:
        month_date = datetime.today().replace(day=1)
    
    # Calculate start and end date of the month
    start_date = month_date
    if month_date.month == 12:
        end_date = month_date.replace(year=month_date.year+1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = month_date.replace(month=month_date.month+1, day=1) - timedelta(days=1)
    
    # Select random drivers
    if num_drivers > len(DRIVERS):
        num_drivers = len(DRIVERS)
    selected_drivers = random.sample(DRIVERS, num_drivers)
    
    # Generate rides
    rows = []
    
    for _ in range(num_rides):
        driver = random.choice(selected_drivers)
        
        # Random date within the month
        day_offset = random.randint(0, (end_date - start_date).days)
        ride_date = start_date + timedelta(days=day_offset)
        
        # Skip some weekend days to make it more realistic
        if ride_date.weekday() >= 5 and random.random() < 0.7:  # 70% chance to skip weekends
            continue
        
        # Generate start and end times
        start_time, end_time = generate_time_pair()
        
        # Add row
        rows.append({
            'Name': driver,
            'Datum': ride_date.strftime('%Y-%m-%d'),
            'Beginn': start_time.strftime('%H:%M'),
            'Ende': end_time.strftime('%H:%M')
        })
    
    # Sort by driver and date
    rows.sort(key=lambda x: (x['Name'], x['Datum']))
    
    # Write to CSV
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['Name', 'Datum', 'Beginn', 'Ende']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Created {filename} with {len(rows)} rides for {num_drivers} drivers")

def create_fahrer_uebersicht(filename, num_drivers):
    """Create a sample Fahrerübersicht (driver overview) CSV file"""
    if num_drivers > len(DRIVERS):
        num_drivers = len(DRIVERS)
    
    selected_drivers = random.sample(DRIVERS, num_drivers)
    
    # Write to CSV
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['Name', 'ID']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for i, driver in enumerate(selected_drivers, 1):
            writer.writerow({
                'Name': driver,
                'ID': f"D{i:03d}"
            })
    
    print(f"Created {filename} with {num_drivers} drivers")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Generate sample data for Arbeitszeitnachweise Generator")
    parser.add_argument("--month", type=str, help="Month to generate data for (format: YYYY-MM)")
    parser.add_argument("--drivers", type=int, default=5, help="Number of drivers to include")
    parser.add_argument("--rides", type=int, default=200, help="Number of rides to generate")
    return parser.parse_args()

def main():
    # Parse arguments
    args = parse_args()
    
    # Ensure samples directory exists
    os.makedirs("samples", exist_ok=True)
    
    # Generate sample files
    create_fahrtenbuch("samples/fahrtenbuch_sample.csv", args.month, args.drivers, args.rides)
    create_fahrer_uebersicht("samples/fahreruebersicht_sample.csv", args.drivers)

if __name__ == "__main__":
    main()