# Arbeitszeitnachweise Generator

A web application for generating work time records (Arbeitszeitnachweise) from driving logs (Fahrtenbuch) for drivers.

## Overview

The Arbeitszeitnachweise Generator processes CSV or Excel files containing driving logs and driver information, calculates work hours, breaks, night hours, and other metrics according to business rules, and generates PDF reports for each driver.

## Features

- **Upload and process** CSV/Excel files with driving logs and driver information
- **Driver management** with active/inactive status
- **User management** with admin and regular user roles
- **Calculation of work metrics** including:
  - Regular work hours
  - Break times
  - Night hours (23:00-06:00)
  - Sunday hours
  - Holiday hours
  - Meal allowances
- **Review and edit** processed data before generating final reports
- **PDF generation** with complete work time records
- **Batch processing** to generate reports for all drivers at once

## Installation

### Prerequisites

- Python 3.11 or higher
- pip (Python package installer)

### Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/arbeitszeitnachweise-generator.git
   cd arbeitszeitnachweise-generator
   ```

2. Create a virtual environment and activate it:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set environment variables (optional):

   ```bash
   # Create a .env file with the following variables
   SECRET_KEY=your-secret-key
   DATABASE_URI=sqlite:///arbeitszeitnachweise.db  # Default SQLite database
   ```

5. Initialize the database:

   ```bash
   python
   >>> from main import app, db
   >>> with app.app_context():
   ...     db.create_all()
   >>> exit()
   ```

## Usage

1. Start the application:

   ```bash
   python main.py
   ```

2. Access the web interface at http://localhost:5000

3. Log in with the default admin account:
   - Username: `admin`
   - Password: `admin`

4. Add drivers through the Drivers management page

5. Upload Fahrtenbuch (driving log) and Fahrerübersicht (driver overview) files

6. Review and edit the processed data if needed

7. Generate PDF reports

## Sample Data

You can generate sample data for testing using the provided script:

```bash
python create_sample_data.py --month 2023-06 --drivers 5 --rides 200
```

This will create:
- `samples/fahrtenbuch_sample.csv` - Sample driving log
- `samples/fahreruebersicht_sample.csv` - Sample driver overview

## File Format Requirements

### Fahrtenbuch (Driving Log)

Required columns:
- Name: Driver name
- Date: Date of the ride (in a recognizable date format)
- Start: Start time of the ride
- End: End time of the ride

### Fahrerübersicht (Driver Overview)

Required columns:
- Name: Driver name
- ID: (Optional) Driver ID or employee number

## Business Rules

- Breaks ≤ 15 minutes are counted as work time
- Breaks > 15 and ≤ 30 minutes count as break time
- Maximum break time per day is capped at 120 minutes (2 hours)
- Consecutive rides with gaps ≤ 15 minutes are merged
- Night hours are calculated for work between 23:00 and 06:00
- Sunday and holiday hours are tracked separately
- Meal allowance is calculated based on total work hours:
  - < 4 hours: €6
  - ≥ 4 hours and < 9 hours: €14
  - ≥ 9 hours: €24

## License

This project is licensed under the MIT License - see the LICENSE file for details.