import os
import pandas as pd
import holidays
from datetime import datetime, timedelta, time
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from models import Driver, db

# German holidays
de_holidays = holidays.DE(prov='HE')  # Hessen state holidays

def normalize_column_names(df):
    """Normalize column names to handle different input formats."""
    normalized_df = df.copy()
    
    # Map of possible column names to standardized names
    name_mapping = {
        # Name variants
        'name': 'name',
        'Name': 'name',
        'NAME': 'name',
        'fahrer': 'name',
        'Fahrer': 'name',
        'driver': 'name',
        'Driver': 'name',
        
        # ID variants
        'id': 'id',
        'ID': 'id',
        'persnum': 'id',
        'Persnum': 'id',
        'personalnummer': 'id',
        'Personalnummer': 'id',
        'personal_id': 'id',
        'Personal-ID': 'id',
        
        # Date variants
        'date': 'date',
        'Date': 'date',
        'datum': 'date',
        'Datum': 'date',
        'tag': 'date',
        'Tag': 'date',
        
        # Start time variants
        'start': 'start',
        'Start': 'start',
        'beginn': 'start',
        'Beginn': 'start',
        'von': 'start',
        'Von': 'start',
        
        # End time variants
        'end': 'end',
        'End': 'end',
        'ende': 'end',
        'Ende': 'end',
        'bis': 'end',
        'Bis': 'end'
    }
    
    # Try to normalize each column name
    for col in normalized_df.columns:
        if col.lower() in name_mapping:
            normalized_df.rename(columns={col: name_mapping[col.lower()]}, inplace=True)
    
    return normalized_df

def validate_required_columns(df, required_columns, file_type):
    """Validate that the dataframe has the required columns."""
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in {file_type}: {', '.join(missing_columns)}")

def parse_time(time_str):
    """Parse time string in various formats."""
    if pd.isna(time_str) or time_str == '':
        return None
    
    # Try different time formats
    formats = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']
    for fmt in formats:
        try:
            return datetime.strptime(str(time_str).strip(), fmt).time()
        except ValueError:
            continue
    
    # Handle numeric format (e.g., 830 for 8:30)
    try:
        time_int = int(str(time_str).strip())
        hours = time_int // 100
        minutes = time_int % 100
        if 0 <= hours < 24 and 0 <= minutes < 60:
            return time(hours, minutes)
    except ValueError:
        pass
    
    raise ValueError(f"Could not parse time: {time_str}")

def time_diff_in_hours(start_time, end_time):
    """Calculate the difference between two time objects in hours."""
    if start_time is None or end_time is None:
        return 0
    
    start_datetime = datetime.combine(datetime.today(), start_time)
    end_datetime = datetime.combine(datetime.today(), end_time)
    
    # Handle overnight shifts
    if end_time < start_time:
        end_datetime += timedelta(days=1)
    
    diff = end_datetime - start_datetime
    return diff.total_seconds() / 3600  # Convert to hours

def calculate_night_hours(start_time, end_time):
    """Calculate night hours (work between 23:00 and 6:00)."""
    if start_time is None or end_time is None:
        return 0
    
    night_start = time(23, 0)
    night_end = time(6, 0)
    
    # Convert times to datetime for calculations
    today = datetime.today().date()
    start_dt = datetime.combine(today, start_time)
    end_dt = datetime.combine(today, end_time)
    night_start_dt = datetime.combine(today, night_start)
    night_end_dt = datetime.combine(today, night_end)
    
    # Handle overnight shifts
    if end_time < start_time:
        end_dt += timedelta(days=1)
    
    # Handle night spanning to next day
    if night_end < night_start:
        night_end_dt += timedelta(days=1)
    
    # Calculate overlap
    night_hours = 0
    
    # Check overlap with night hours (23:00-6:00)
    if start_dt < night_end_dt and end_dt > night_start_dt:
        overlap_start = max(start_dt, night_start_dt)
        overlap_end = min(end_dt, night_end_dt)
        
        if overlap_end <= overlap_start:
            # If end_dt is before start_dt (next day), adjust
            if night_end < night_start and overlap_end.time() <= night_end:
                overlap_end += timedelta(days=1)
        
        night_hours = (overlap_end - overlap_start).total_seconds() / 3600
    
    return max(0, night_hours)

def merge_consecutive_rides(rides, max_gap_minutes=15):
    """Merge consecutive rides with small gaps between them."""
    if not rides:
        return []
    
    # Sort rides by start time
    sorted_rides = sorted(rides, key=lambda x: x['start'])
    merged_rides = [sorted_rides[0]]
    
    for ride in sorted_rides[1:]:
        last_ride = merged_rides[-1]
        
        # Calculate gap between rides
        last_end = datetime.combine(datetime.today(), last_ride['end'])
        current_start = datetime.combine(datetime.today(), ride['start'])
        
        # Handle overnight shifts
        if last_ride['end'] > last_ride['start'] and ride['start'] < last_ride['start']:
            current_start += timedelta(days=1)
        
        gap_minutes = (current_start - last_end).total_seconds() / 60
        
        # Merge if gap is small enough
        if gap_minutes <= max_gap_minutes:
            # Update end time of the last ride
            last_ride['end'] = max(last_ride['end'], ride['end'])
        else:
            merged_rides.append(ride)
    
    return merged_rides

def calculate_break_time(rides, max_break_minutes=120):
    """Calculate total break time between rides."""
    if not rides or len(rides) <= 1:
        return 0
    
    # Sort rides by start time
    sorted_rides = sorted(rides, key=lambda x: x['start'])
    total_break_minutes = 0
    
    for i in range(1, len(sorted_rides)):
        prev_ride = sorted_rides[i-1]
        curr_ride = sorted_rides[i]
        
        # Calculate gap between rides
        prev_end = datetime.combine(datetime.today(), prev_ride['end'])
        curr_start = datetime.combine(datetime.today(), curr_ride['start'])
        
        # Handle overnight shifts
        if prev_ride['end'] > prev_ride['start'] and curr_ride['start'] < prev_ride['start']:
            curr_start += timedelta(days=1)
        
        gap_minutes = (curr_start - prev_end).total_seconds() / 60
        
        # Count as break if gap is more than 15 minutes but less than max_break_minutes
        if 15 < gap_minutes <= max_break_minutes:
            total_break_minutes += gap_minutes
    
    # Cap total break time
    return min(total_break_minutes, max_break_minutes) / 60  # Convert to hours

def calculate_sunday_hours(date, work_hours):
    """Calculate Sunday hours based on the date."""
    if date.weekday() == 6:  # Sunday is 6 in Python's datetime.weekday()
        return work_hours
    return 0

def calculate_holiday_hours(date, work_hours):
    """Calculate holiday hours based on the date."""
    if date in de_holidays:
        return work_hours
    return 0

def calculate_meal_allowance(total_hours):
    """Calculate meal allowance based on total work hours."""
    if total_hours < 4:
        return 6
    elif total_hours < 9:
        return 14
    else:
        return 24

def process_files(fahrtenbuch_path, fahreruebersicht_path, month_year, include_inactive=False, special_days_text=''):
    """Process the uploaded files and calculate work hours."""
    # Load and normalize files
    if fahrtenbuch_path.endswith('.csv'):
        fahrtenbuch_df = pd.read_csv(fahrtenbuch_path)
    else:
        fahrtenbuch_df = pd.read_excel(fahrtenbuch_path)
    
    if fahreruebersicht_path.endswith('.csv'):
        fahreruebersicht_df = pd.read_csv(fahreruebersicht_path)
    else:
        fahreruebersicht_df = pd.read_excel(fahreruebersicht_path)
    
    # Normalize column names
    fahrtenbuch_df = normalize_column_names(fahrtenbuch_df)
    fahreruebersicht_df = normalize_column_names(fahreruebersicht_df)
    
    # Validate required columns
    validate_required_columns(fahrtenbuch_df, ['name', 'date', 'start', 'end'], 'Fahrtenbuch')
    validate_required_columns(fahreruebersicht_df, ['name'], 'Fahrerübersicht')
    
    # Process special days
    special_days = {}
    if special_days_text:
        for line in special_days_text.strip().split('\n'):
            if ',' in line:
                date_str, status = line.strip().split(',', 1)
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    special_days[date] = status.strip()
                except ValueError:
                    continue
    
    # Get active drivers from database or use from fahreruebersicht
    drivers_db = Driver.query.filter_by(is_active=True).all() if not include_inactive else Driver.query.all()
    driver_names = [driver.name for driver in drivers_db]
    
    # If no drivers in database, use the ones from fahreruebersicht
    if not driver_names:
        driver_names = fahreruebersicht_df['name'].unique().tolist()
    
    # Filter by drivers and month
    month_start = month_year.replace(day=1)
    if month_year.month == 12:
        month_end = month_year.replace(year=month_year.year+1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = month_year.replace(month=month_year.month+1, day=1) - timedelta(days=1)
    
    # Convert date column to datetime
    date_formats = ['%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y', '%d/%m/%Y']
    for fmt in date_formats:
        try:
            fahrtenbuch_df['date'] = pd.to_datetime(fahrtenbuch_df['date'], format=fmt)
            break
        except ValueError:
            continue
    else:
        # If none of the formats worked, try the default parser
        fahrtenbuch_df['date'] = pd.to_datetime(fahrtenbuch_df['date'])
    
    # Filter by month
    fahrtenbuch_df = fahrtenbuch_df[
        (fahrtenbuch_df['date'] >= pd.Timestamp(month_start)) & 
        (fahrtenbuch_df['date'] <= pd.Timestamp(month_end))
    ]
    
    # Process each driver
    processed_data = {}
    
    for driver_name in driver_names:
        # Filter rides for this driver
        driver_rides = fahrtenbuch_df[fahrtenbuch_df['name'] == driver_name]
        
        if driver_rides.empty and driver_name not in special_days.values():
            continue
        
        # Initialize data structure for all days in the month
        days_data = []
        current_date = month_start
        
        while current_date <= month_end:
            day_data = {
                'date': current_date,
                'day_name': current_date.strftime('%A'),
                'work_hours': 0,
                'break_time': 0,
                'night_hours': 0,
                'sunday_hours': 0,
                'holiday_hours': 0,
                'is_weekend': current_date.weekday() >= 5,
                'is_holiday': current_date in de_holidays,
                'holiday_name': de_holidays.get(current_date),
                'status': special_days.get(current_date)
            }
            
            # Get rides for this day
            day_rides = driver_rides[driver_rides['date'].dt.date == current_date]
            
            if not day_rides.empty and not day_data['status']:  # Process rides if not a special day
                rides = []
                for _, ride in day_rides.iterrows():
                    try:
                        start_time = parse_time(ride['start'])
                        end_time = parse_time(ride['end'])
                        rides.append({
                            'start': start_time,
                            'end': end_time
                        })
                    except ValueError as e:
                        continue
                
                # Merge consecutive rides
                merged_rides = merge_consecutive_rides(rides)
                
                # Calculate work hours
                work_hours = sum(time_diff_in_hours(ride['start'], ride['end']) for ride in merged_rides)
                
                # Calculate break time
                break_time = calculate_break_time(rides)
                
                # Calculate night hours
                night_hours = sum(calculate_night_hours(ride['start'], ride['end']) for ride in merged_rides)
                
                # Update day data
                day_data['work_hours'] = round(work_hours, 2)
                day_data['break_time'] = round(break_time, 2)
                day_data['night_hours'] = round(night_hours, 2)
                day_data['sunday_hours'] = round(calculate_sunday_hours(current_date, work_hours), 2)
                day_data['holiday_hours'] = round(calculate_holiday_hours(current_date, work_hours), 2)
            
            days_data.append(day_data)
            current_date += timedelta(days=1)
        
        # Calculate totals
        total_work_hours = sum(day['work_hours'] for day in days_data)
        total_break_time = sum(day['break_time'] for day in days_data)
        total_night_hours = sum(day['night_hours'] for day in days_data)
        total_sunday_hours = sum(day['sunday_hours'] for day in days_data)
        total_holiday_hours = sum(day['holiday_hours'] for day in days_data)
        
        # Calculate meal allowance
        meal_allowance = calculate_meal_allowance(total_work_hours)
        
        processed_data[driver_name] = {
            'days': days_data,
            'total_work_hours': round(total_work_hours, 2),
            'total_break_time': round(total_break_time, 2),
            'total_night_hours': round(total_night_hours, 2),
            'total_sunday_hours': round(total_sunday_hours, 2),
            'total_holiday_hours': round(total_holiday_hours, 2),
            'meal_allowance': meal_allowance
        }
    
    return processed_data

def format_hours(hours):
    """Format hours as HH:MM."""
    if hours is None or pd.isna(hours):
        return '0:00'
    
    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}:{m:02d}"

def generate_pdf(driver_name, driver_data, month_year_str, output_path):
    """Generate a PDF report for a driver's work time."""
    # Create PDF document
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    # Register fonts if needed
    # pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    header_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Parse month and year
    month_year = datetime.strptime(month_year_str, '%Y-%m')
    month_name = month_year.strftime('%B %Y')
    
    # Create content
    content = []
    
    # Add title
    content.append(Paragraph(f"Arbeitszeitnachweis - {month_name}", title_style))
    content.append(Spacer(1, 10))
    
    # Add driver info
    content.append(Paragraph(f"Fahrer: {driver_name}", header_style))
    content.append(Spacer(1, 10))
    
    # Create table data
    data = [[
        "Datum", "Tag", "Arbeitszeit", "Pause", "Nachtarbeit",
        "Sonntagsarbeit", "Feiertagsarbeit", "Status"
    ]]
    
    # Add days
    for day in driver_data['days']:
        row = [
            day['date'].strftime('%d.%m.%Y'),
            day['day_name'],
            format_hours(day['work_hours']),
            format_hours(day['break_time']),
            format_hours(day['night_hours']),
            format_hours(day['sunday_hours']),
            format_hours(day['holiday_hours']),
            day['status'] if day['status'] else ('Feiertag' if day['is_holiday'] else '')
        ]
        data.append(row)
    
    # Add totals
    data.append([
        "Summe", "", 
        format_hours(driver_data['total_work_hours']),
        format_hours(driver_data['total_break_time']),
        format_hours(driver_data['total_night_hours']),
        format_hours(driver_data['total_sunday_hours']),
        format_hours(driver_data['total_holiday_hours']),
        ""
    ])
    
    # Create table
    table = Table(data, repeatRows=1)
    
    # Style the table
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.beige),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 1), (-2, -1), 'RIGHT'),
    ])
    
    # Add row colors for weekends and holidays
    for i, day in enumerate(driver_data['days'], 1):
        if day['is_weekend']:
            table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightgrey)
        if day['is_holiday']:
            table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightpink)
        if day['status']:
            if day['status'].lower() == 'sick':
                table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightblue)
            elif day['status'].lower() == 'vacation':
                table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightgreen)
    
    table.setStyle(table_style)
    content.append(table)
    content.append(Spacer(1, 20))
    
    # Add meal allowance
    content.append(Paragraph(f"Verpflegungspauschale: {driver_data['meal_allowance']} €", normal_style))
    content.append(Spacer(1, 30))
    
    # Add signature fields
    signature_data = [
        ['Datum, Unterschrift Arbeitnehmer', 'Datum, Unterschrift Arbeitgeber'],
        ['_______________________________', '_______________________________']
    ]
    signature_table = Table(signature_data, colWidths=[doc.width/2.2]*2)
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    content.append(signature_table)
    
    # Build the PDF
    doc.build(content)
    
    return output_path
