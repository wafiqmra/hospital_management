from flask import Flask, render_template, request, send_file
import pandas as pd
import mysql.connector
from datetime import datetime, timedelta
import io
import json

app = Flask(__name__)

# ------------------------------
# FUNGSI KONEKSI DATABASE
# ------------------------------
def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="hospital"
    )

# ------------------------------
# LOAD DATA FUNCTIONS
# ------------------------------
def load_doctor_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM doctor_schedule"
        df = pd.read_sql(query, conn)
        conn.close()

        print("Kolom di tabel doctor_schedule:", df.columns.tolist())
        print(f"Jumlah baris data dokter: {len(df)}")

        if df.empty:
            print("⚠️ Data doctor_schedule kosong.")
            return pd.DataFrame(columns=[
                'schedule_id', 'doctor_id', 'name', 'specialization',
                'schedule_day', 'start_time', 'end_time', 'room_id'
            ])

        if 'doctor_id' not in df.columns:
            print("⚠️ Kolom 'doctor_id' tidak ditemukan! Menambahkan dummy ID...")
            df['doctor_id'] = range(1, len(df) + 1)

        return df
    except Exception as e:
        print(f"[ERROR] Gagal load data dokter: {e}")
        return pd.DataFrame(columns=[
            'schedule_id', 'doctor_id', 'name', 'specialization',
            'schedule_day', 'start_time', 'end_time', 'room_id'
        ])

def load_room_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM rooms"
        df = pd.read_sql(query, conn)
        conn.close()

        total_rooms = len(df)
        occupied_rooms = len(df[df['current_occupancy'] > 0]) if 'current_occupancy' in df.columns else 0
        available_rooms = total_rooms - occupied_rooms

        room_stats = {}
        if 'room_type' in df.columns:
            for room_type in df['room_type'].unique():
                type_data = df[df['room_type'] == room_type]
                total_type = len(type_data)
                occupied_type = len(type_data[type_data['current_occupancy'] > 0]) if 'current_occupancy' in df.columns else 0
                occupancy_rate = (occupied_type / total_type * 100) if total_type > 0 else 0
                room_stats[room_type] = {
                    'total': total_type,
                    'occupied': occupied_type,
                    'available': total_type - occupied_type,
                    'occupancy_rate': round(occupancy_rate, 1)
                }

        return df, total_rooms, occupied_rooms, available_rooms, room_stats

    except Exception as e:
        print(f"[ERROR] Gagal load data ruangan: {e}")
        return pd.DataFrame(), 0, 0, 0, {}

def load_patient_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM patients"
        df = pd.read_sql(query, conn)
        conn.close()

        if 'birth_date' in df.columns:
            df['birth_date'] = pd.to_datetime(df['birth_date'], errors='coerce')
            today = datetime.today()
            df['age'] = df['birth_date'].apply(
                lambda x: today.year - x.year - ((today.month, today.day) < (x.month, x.day)) 
                if pd.notnull(x) else 0
            )
        else:
            df['age'] = 0

        def categorize_age(age):
            if age < 18:
                return 'Anak (<18)'
            elif 18 <= age < 40:
                return 'Dewasa Muda (18-39)'
            elif 40 <= age < 60:
                return 'Dewasa (40-59)'
            else:
                return 'Lansia (60+)'
        
        df['age_group'] = df['age'].apply(categorize_age)

        total_patients = len(df)
        gender_dist = df['gender'].value_counts().to_dict() if 'gender' in df.columns else {}
        payment_dist = df['payment_type'].value_counts().to_dict() if 'payment_type' in df.columns else {}
        insurance_dist = df['insurance_provider'].value_counts().to_dict() if 'insurance_provider' in df.columns else {}
        city_dist = df['city'].value_counts().head(10).to_dict() if 'city' in df.columns else {}

        return df, total_patients, gender_dist, payment_dist, insurance_dist, city_dist

    except Exception as e:
        print(f"[ERROR] Gagal load data pasien: {e}")
        return pd.DataFrame(), 0, {}, {}, {}, {}

def load_pharmacy_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM pharmacy_stock"
        df = pd.read_sql(query, conn)
        conn.close()

        if df.empty:
            return pd.DataFrame(columns=[
                'drug_id','drug_name','category','stock_in','stock_out','stock_date','expiry_date','supplier'
            ]), 0, 0, 0, 0

        # Hitung stok saat ini
        if 'stock_in' in df.columns and 'stock_out' in df.columns:
            df['current_stock'] = df['stock_in'] - df['stock_out']
        else:
            df['current_stock'] = 0

        # Statistik
        total_medicines = len(df)
        low_stock_medicines = len(df[df['current_stock'] <= 5])
        out_of_stock_medicines = len(df[df['current_stock'] <= 0])
        pharmacy_categories = df['category'].nunique() if 'category' in df.columns else 0

        return df, total_medicines, low_stock_medicines, out_of_stock_medicines, pharmacy_categories

    except Exception as e:
        print(f"[ERROR] Gagal load data pharmacy: {e}")
        return pd.DataFrame(columns=[
            'drug_id','drug_name','category','stock_in','stock_out','stock_date','expiry_date','supplier'
        ]), 0, 0, 0, 0

def load_staff_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM staff"
        df = pd.read_sql(query, conn)
        conn.close()

        # Hitung years of service
        if 'hire_date' in df.columns:
            df['hire_date'] = pd.to_datetime(df['hire_date'], errors='coerce')
            today = datetime.today()
            df['years_of_service'] = ((today - df['hire_date']).dt.days / 365.25).round(1)
        else:
            df['years_of_service'] = 0

        # Hitung statistik
        total_staff = len(df)
        active_staff = len(df[df['active'] == 'True']) if 'active' in df.columns else 0
        inactive_staff = total_staff - active_staff
        staff_departments_count = df['department'].nunique() if 'department' in df.columns else 0

        return df, total_staff, active_staff, inactive_staff, staff_departments_count

    except Exception as e:
        print(f"[ERROR] Gagal load data staff: {e}")
        return pd.DataFrame(columns=[
            'staff_id', 'name', 'role', 'department', 'hire_date', 'active', 'years_of_service'
        ]), 0, 0, 0, 0

def load_lab_tests_data():
    try:
        conn = get_connection()
        
        # Query dengan JOIN ke tabel patients untuk mendapatkan nama pasien
        query = """
        SELECT lt.*, p.name as patient_name 
        FROM lab_tests lt 
        LEFT JOIN patients p ON lt.patient_id = p.patient_id
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # Hitung statistik
        total_lab_tests = len(df)
        pending_tests = len(df[df['result_status'] == 'Pending']) if 'result_status' in df.columns else 0
        completed_tests = len(df[df['result_status'] == 'Completed']) if 'result_status' in df.columns else 0
        lab_test_types_count = df['test_type'].nunique() if 'test_type' in df.columns else 0

        return df, total_lab_tests, pending_tests, completed_tests, lab_test_types_count

    except Exception as e:
        print(f"[ERROR] Gagal load data lab tests: {e}")
        return pd.DataFrame(columns=[
            'test_id', 'patient_id', 'patient_name', 'test_type', 
            'scheduled_date', 'result_date', 'result_status', 'lab_staff_id'
        ]), 0, 0, 0, 0

# ------------------------------
# ROUTES
# ------------------------------

@app.route('/')
def index():
    return dashboard()

@app.route('/dashboard')
def dashboard():
    """Dashboard utama dengan ringkasan hari ini"""
    try:
        today = datetime.today().date()
        
        # Data dokter hari ini
        df_doctor = load_doctor_data()
        if 'schedule_day' in df_doctor.columns:
            today_doctors = df_doctor[df_doctor['schedule_day'] == today.strftime('%A')]
            total_today_doctors = len(today_doctors)
        else:
            total_today_doctors = 0
            today_doctors = pd.DataFrame()
        
        # Data ruangan
        df_room, total_rooms, occupied_rooms, available_rooms, room_stats = load_room_data()
        occupancy_rate = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
        
        # Data pasien hari ini
        try:
            conn = get_connection()
            query = "SELECT COUNT(*) as count FROM patients WHERE DATE(registration_date) = %s"
            df_today_patients = pd.read_sql(query, conn, params=[today])
            today_patients = df_today_patients.iloc[0]['count']
            conn.close()
        except Exception as e:
            print(f"Error loading today patients: {e}")
            today_patients = 0
        
        # Data pharmacy
        df_pharmacy, total_medicines, low_stock_medicines, out_of_stock_medicines, pharmacy_categories = load_pharmacy_data()
        
        # Data lab tests hari ini
        df_lab, total_lab_tests, pending_tests, completed_tests, lab_test_types_count = load_lab_tests_data()
        if 'scheduled_date' in df_lab.columns:
            today_lab_tests = df_lab[df_lab['scheduled_date'] == today.strftime('%Y-%m-%d')]
            total_today_tests = len(today_lab_tests)
        else:
            total_today_tests = 0
            today_lab_tests = pd.DataFrame()
        
        # Data staff aktif
        df_staff, total_staff, active_staff, inactive_staff, staff_departments_count = load_staff_data()
        
        # Data untuk chart dokter hari ini
        today_doctors_spec = today_doctors['specialization'].value_counts().to_dict() if 'specialization' in today_doctors.columns else {}
        
        # Data untuk chart tes lab hari ini
        today_tests_status = today_lab_tests['result_status'].value_counts().to_dict() if 'result_status' in today_lab_tests.columns else {}

        # Data untuk chart tambahan
        time_slots = {}
        room_type_occupancy = {}
        
        # Statistik untuk cards
        stats = {
            'today_doctors': total_today_doctors,
            'today_patients': today_patients,
            'today_tests': total_today_tests,
            'total_rooms': total_rooms,
            'occupied_rooms': occupied_rooms,
            'available_rooms': available_rooms,
            'occupancy_rate': round(occupancy_rate, 1),
            'total_medicines': total_medicines,
            'low_stock_medicines': low_stock_medicines,
            'out_of_stock_medicines': out_of_stock_medicines,
            'active_staff': active_staff,
            'pending_tests': pending_tests,
            'total_patients': len(load_patient_data()[0]),
            'total_lab_tests': total_lab_tests
        }
        
        return render_template(
            'dashboard.html',
            stats=stats,
            today_doctors_spec=today_doctors_spec,
            today_tests_status=today_tests_status,
            time_slots=time_slots,
            room_stats=room_stats,
            today=today,
            now=datetime.now()
        )
        
    except Exception as e:
        print(f"Dashboard error: {e}")
        return render_template(
            'dashboard.html',
            stats={},
            today_doctors_spec={},
            today_tests_status={},
            time_slots={},
            room_stats={},
            today=datetime.today().date(),
            now=datetime.now()
        )

@app.route('/doctor')
def doctor_tab():
    df_doctor = load_doctor_data()

    # Filter data
    specialization = request.args.get('specialization', 'All')
    day = request.args.get('day', 'All')
    search_doctor = request.args.get('search_doctor', '')

    filtered_doctor_df = df_doctor.copy()
    if specialization != 'All' and 'specialization' in filtered_doctor_df.columns:
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['specialization'] == specialization]
    if day != 'All' and 'schedule_day' in filtered_doctor_df.columns:
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['schedule_day'] == day]
    if search_doctor and 'name' in filtered_doctor_df.columns:
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['name'].str.contains(search_doctor, case=False, na=False)]

    # Statistik
    total_doctors = filtered_doctor_df['doctor_id'].nunique() if 'doctor_id' in filtered_doctor_df.columns else 0
    total_schedules = len(filtered_doctor_df)
    total_specializations = filtered_doctor_df['specialization'].nunique() if 'specialization' in filtered_doctor_df.columns else 0
    total_doctor_rooms = filtered_doctor_df['room_id'].nunique() if 'room_id' in filtered_doctor_df.columns else 0

    # Data untuk chart
    spec_count = filtered_doctor_df['specialization'].value_counts().to_dict() if 'specialization' in filtered_doctor_df.columns else {}
    day_count = filtered_doctor_df['schedule_day'].value_counts().to_dict() if 'schedule_day' in filtered_doctor_df.columns else {}
    
    # Heatmap data
    if 'schedule_day' in filtered_doctor_df.columns and 'specialization' in filtered_doctor_df.columns:
        heatmap_data = (
            filtered_doctor_df.groupby(['schedule_day', 'specialization'])
            .size()
            .reset_index(name='count')
        )
    else:
        heatmap_data = pd.DataFrame(columns=['schedule_day', 'specialization', 'count'])
    
    # Room usage data
    if 'room_id' in filtered_doctor_df.columns:
        room_usage = (
            filtered_doctor_df.groupby('room_id')
            .size()
            .reset_index(name='count')
            .sort_values(by='count', ascending=False)
            .head(10)
        )
    else:
        room_usage = pd.DataFrame(columns=['room_id', 'count'])

    # Dropdown filter
    specializations = ['All']
    days = ['All']
    
    if 'specialization' in df_doctor.columns:
        specializations += sorted(df_doctor['specialization'].dropna().unique().tolist())
    if 'schedule_day' in df_doctor.columns:
        days += sorted(df_doctor['schedule_day'].dropna().unique().tolist())

    # Tabel data
    table_columns = ['name', 'specialization', 'schedule_day', 'start_time', 'end_time', 'room_id']
    available_columns = [col for col in table_columns if col in filtered_doctor_df.columns]
    table_data = filtered_doctor_df[available_columns].to_dict('records')

    return render_template(
        'doctor_tab.html',
        total_doctors=total_doctors,
        total_schedules=total_schedules,
        total_specializations=total_specializations,
        total_doctor_rooms=total_doctor_rooms,
        spec_count=spec_count,
        day_count=day_count,
        heatmap_data=heatmap_data.to_dict('records'),
        room_usage_data=room_usage.to_dict('records'),
        specializations=specializations,
        days=days,
        current_specialization=specialization,
        current_day=day,
        search_doctor=search_doctor,
        table_data=table_data,
        table_count=len(table_data),
        now=datetime.now()
    )

@app.route('/room')
def room_tab():
    df_room, total_rooms, occupied_rooms, available_rooms, room_stats = load_room_data()

    # Data untuk chart
    room_type_data = {}
    occupancy_data = {}
    
    for room_type, stats in room_stats.items():
        room_type_data[room_type] = stats['total']
        occupancy_data[room_type] = stats['occupancy_rate']

    # Tabel data
    room_table_data = df_room.to_dict('records')

    return render_template(
        'room_tab.html',
        total_rooms=total_rooms,
        occupied_rooms=occupied_rooms,
        available_rooms=available_rooms,
        room_stats=room_stats,
        room_type_data=room_type_data,
        occupancy_data=occupancy_data,
        room_table_data=room_table_data,
        room_table_count=len(room_table_data),
        now=datetime.now()
    )

@app.route('/patient')
def patient_tab():
    df_patient, total_patients, gender_dist, payment_dist, insurance_dist, city_dist = load_patient_data()

    # Age group data
    age_group_count = df_patient['age_group'].value_counts().to_dict() if 'age_group' in df_patient.columns else {}

    # Tabel data
    table_columns = ['patient_id', 'name', 'gender', 'age', 'city', 'payment_type', 'insurance_provider']
    available_columns = [col for col in table_columns if col in df_patient.columns]
    patient_table_data = df_patient[available_columns].to_dict('records')

    return render_template(
        'patient_tab.html',
        total_patients=total_patients,
        gender_dist=gender_dist,
        payment_dist=payment_dist,
        insurance_dist=insurance_dist,
        city_dist=city_dist,
        age_group_count=age_group_count,
        patient_table_data=patient_table_data,
        patient_table_count=len(patient_table_data),
        now=datetime.now()
    )

@app.route('/pharmacy')
def pharmacy_tab():
    df_pharmacy, total_medicines, low_stock_medicines, out_of_stock_medicines, pharmacy_categories = load_pharmacy_data()

    # Data untuk chart
    category_count = df_pharmacy['category'].value_counts().to_dict() if 'category' in df_pharmacy.columns else {}
    
    # Supplier data
    supplier_count = df_pharmacy['supplier'].value_counts().head(10).to_dict() if 'supplier' in df_pharmacy.columns else {}
    
    # Expiry data
    if 'expiry_date' in df_pharmacy.columns:
        df_pharmacy['expiry_date'] = pd.to_datetime(df_pharmacy['expiry_date'], errors='coerce')
        upcoming_expiry = df_pharmacy[df_pharmacy['expiry_date'] <= (datetime.today() + timedelta(days=30))]
        expiry_data = upcoming_expiry[['drug_name', 'current_stock']].to_dict('records') if 'drug_name' in upcoming_expiry.columns else []
    else:
        expiry_data = []

    # Stock status
    stock_status = {
        'In Stock': len(df_pharmacy[df_pharmacy['current_stock'] > 5]),
        'Low Stock': len(df_pharmacy[(df_pharmacy['current_stock'] <= 5) & (df_pharmacy['current_stock'] > 0)]),
        'Out of Stock': len(df_pharmacy[df_pharmacy['current_stock'] <= 0])
    }

    # Tabel data pharmacy
    pharmacy_table_data = df_pharmacy.to_dict('records')

    return render_template(
        'pharmacy_tab.html',
        total_medicines=total_medicines,
        low_stock_medicines=low_stock_medicines,
        out_of_stock_medicines=out_of_stock_medicines,
        pharmacy_categories=pharmacy_categories,
        category_count=category_count,
        supplier_count=supplier_count,
        expiry_data=expiry_data,
        stock_status=stock_status,
        pharmacy_table_data=pharmacy_table_data,
        pharmacy_table_count=len(pharmacy_table_data),
        now=datetime.now()
    )

@app.route('/lab')
def lab_tab():
    df_lab, total_lab_tests, pending_tests, completed_tests, lab_test_types_count = load_lab_tests_data()

    # Filter lab tests
    test_type = request.args.get('test_type', 'All')
    result_status = request.args.get('result_status', 'All')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    filtered_lab_df = df_lab.copy()
    if test_type != 'All' and 'test_type' in filtered_lab_df.columns:
        filtered_lab_df = filtered_lab_df[filtered_lab_df['test_type'] == test_type]
    if result_status != 'All' and 'result_status' in filtered_lab_df.columns:
        filtered_lab_df = filtered_lab_df[filtered_lab_df['result_status'] == result_status]
    if start_date and 'scheduled_date' in filtered_lab_df.columns:
        filtered_lab_df = filtered_lab_df[filtered_lab_df['scheduled_date'] >= start_date]
    if end_date and 'scheduled_date' in filtered_lab_df.columns:
        filtered_lab_df = filtered_lab_df[filtered_lab_df['scheduled_date'] <= end_date]

    # Data untuk chart
    test_type_count = filtered_lab_df['test_type'].value_counts().to_dict() if 'test_type' in filtered_lab_df.columns else {}
    result_status_count = filtered_lab_df['result_status'].value_counts().to_dict() if 'result_status' in filtered_lab_df.columns else {}
    
    # Daily tests data
    if 'scheduled_date' in filtered_lab_df.columns:
        daily_tests = filtered_lab_df.groupby('scheduled_date').size().reset_index(name='count')
    else:
        daily_tests = pd.DataFrame(columns=['scheduled_date', 'count'])
    
    # Lab staff data
    lab_staff_count = filtered_lab_df['lab_staff_id'].value_counts().head(10).to_dict() if 'lab_staff_id' in filtered_lab_df.columns else {}

    # Dropdown filter
    lab_test_types = ['All']
    lab_result_statuses = ['All']
    
    if 'test_type' in df_lab.columns:
        lab_test_types += sorted(df_lab['test_type'].dropna().unique().tolist())
    if 'result_status' in df_lab.columns:
        lab_result_statuses += sorted(df_lab['result_status'].dropna().unique().tolist())

    # Tabel data lab tests
    lab_table_data = filtered_lab_df.to_dict('records')

    return render_template(
        'lab_tab.html',
        total_lab_tests=total_lab_tests,
        pending_tests=pending_tests,
        completed_tests=completed_tests,
        lab_test_types_count=lab_test_types_count,
        test_type_count=test_type_count,
        result_status_count=result_status_count,
        daily_tests_data=daily_tests.to_dict('records'),
        lab_staff_count=lab_staff_count,
        lab_table_data=lab_table_data,
        lab_table_count=len(lab_table_data),
        lab_test_types=lab_test_types,
        lab_result_statuses=lab_result_statuses,
        current_test_type=test_type,
        current_result_status=result_status,
        current_start_date=start_date,
        current_end_date=end_date,
        now=datetime.now()
    )

@app.route('/staff')
def staff_tab():
    df_staff, total_staff, active_staff, inactive_staff, staff_departments_count = load_staff_data()

    # Filter staff
    staff_role = request.args.get('staff_role', 'All')
    staff_department = request.args.get('staff_department', 'All')
    staff_status = request.args.get('staff_status', 'All')
    search_staff = request.args.get('search_staff', '')

    filtered_staff_df = df_staff.copy()
    if staff_role != 'All' and 'role' in filtered_staff_df.columns:
        filtered_staff_df = filtered_staff_df[filtered_staff_df['role'] == staff_role]
    if staff_department != 'All' and 'department' in filtered_staff_df.columns:
        filtered_staff_df = filtered_staff_df[filtered_staff_df['department'] == staff_department]
    if staff_status != 'All' and 'active' in filtered_staff_df.columns:
        status_filter = 'True' if staff_status == 'Active' else 'False'
        filtered_staff_df = filtered_staff_df[filtered_staff_df['active'] == status_filter]
    if search_staff and 'name' in filtered_staff_df.columns:
        filtered_staff_df = filtered_staff_df[filtered_staff_df['name'].str.contains(search_staff, case=False, na=False)]

    # Data untuk chart
    role_count = filtered_staff_df['role'].value_counts().to_dict() if 'role' in filtered_staff_df.columns else {}
    dept_count = filtered_staff_df['department'].value_counts().to_dict() if 'department' in filtered_staff_df.columns else {}
    
    # Hire year data
    if 'hire_date' in filtered_staff_df.columns:
        filtered_staff_df['hire_year'] = filtered_staff_df['hire_date'].dt.year
        hire_year_count = filtered_staff_df['hire_year'].value_counts().sort_index().to_dict()
    else:
        hire_year_count = {}
    
    # Status data
    active_count = len(filtered_staff_df[filtered_staff_df['active'] == 'True']) if 'active' in filtered_staff_df.columns else 0
    inactive_count = len(filtered_staff_df[filtered_staff_df['active'] == 'False']) if 'active' in filtered_staff_df.columns else 0

    # Dropdown filter
    staff_roles = ['All']
    staff_departments = ['All']
    staff_statuses = ['All', 'Active', 'Inactive']
    
    if 'role' in df_staff.columns:
        staff_roles += sorted(df_staff['role'].dropna().unique().tolist())
    if 'department' in df_staff.columns:
        staff_departments += sorted(df_staff['department'].dropna().unique().tolist())

    # Tabel data staff
    staff_table_data = filtered_staff_df.to_dict('records')

    return render_template(
        'staff_tab.html',
        total_staff=total_staff,
        active_staff=active_staff,
        inactive_staff=inactive_staff,
        staff_departments_count=staff_departments_count,
        role_count=role_count,
        dept_count=dept_count,
        hire_year_count=hire_year_count,
        active_count=active_count,
        inactive_count=inactive_count,
        staff_table_data=staff_table_data,
        staff_table_count=len(staff_table_data),
        staff_roles=staff_roles,
        staff_departments=staff_departments,
        staff_statuses=staff_statuses,
        current_staff_role=staff_role,
        current_staff_department=staff_department,
        current_staff_status=staff_status,
        search_staff=search_staff,
        now=datetime.now()
    )

# ------------------------------
# EXPORT FUNCTIONS
# ------------------------------

@app.route('/export')
def export_doctor_csv():
    df_doctor = load_doctor_data()
    output = io.BytesIO()
    
    # Apply filters if any
    specialization = request.args.get('specialization', 'All')
    day = request.args.get('day', 'All')
    search_doctor = request.args.get('search_doctor', '')
    
    filtered_df = df_doctor.copy()
    if specialization != 'All' and 'specialization' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['specialization'] == specialization]
    if day != 'All' and 'schedule_day' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['schedule_day'] == day]
    if search_doctor and 'name' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['name'].str.contains(search_doctor, case=False, na=False)]
    
    filtered_df.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'doctor_schedules_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/export_rooms')
def export_rooms_csv():
    df_room, _, _, _, _ = load_room_data()
    output = io.BytesIO()
    df_room.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'room_data_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/export_patients')
def export_patients_csv():
    df_patient, _, _, _, _, _ = load_patient_data()
    output = io.BytesIO()
    df_patient.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'patient_data_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/export_pharmacy')
def export_pharmacy_csv():
    df_pharmacy, _, _, _, _ = load_pharmacy_data()
    output = io.BytesIO()
    df_pharmacy.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'pharmacy_data_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/export_lab_tests')
def export_lab_tests_csv():
    df_lab, _, _, _, _ = load_lab_tests_data()
    output = io.BytesIO()
    
    # Apply filters if any
    test_type = request.args.get('test_type', 'All')
    result_status = request.args.get('result_status', 'All')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    filtered_df = df_lab.copy()
    if test_type != 'All' and 'test_type' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['test_type'] == test_type]
    if result_status != 'All' and 'result_status' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['result_status'] == result_status]
    if start_date and 'scheduled_date' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['scheduled_date'] >= start_date]
    if end_date and 'scheduled_date' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['scheduled_date'] <= end_date]
    
    filtered_df.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'lab_tests_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/export_staff')
def export_staff_csv():
    df_staff, _, _, _, _ = load_staff_data()
    output = io.BytesIO()
    
    # Apply filters if any
    staff_role = request.args.get('role', 'All')
    staff_department = request.args.get('department', 'All')
    staff_status = request.args.get('status', 'All')
    search_staff = request.args.get('search', '')
    
    filtered_df = df_staff.copy()
    if staff_role != 'All' and 'role' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['role'] == staff_role]
    if staff_department != 'All' and 'department' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['department'] == staff_department]
    if staff_status != 'All' and 'active' in filtered_df.columns:
        status_filter = 'True' if staff_status == 'Active' else 'False'
        filtered_df = filtered_df[filtered_df['active'] == status_filter]
    if search_staff and 'name' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['name'].str.contains(search_staff, case=False, na=False)]
    
    filtered_df.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'staff_data_{datetime.now().strftime("%Y%m%d")}.csv'
    )

# ------------------------------
# CONTEXT PROCESSORS
# ------------------------------

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.context_processor  
def inject_request():
    return {'request': request}

if __name__ == '__main__':
    app.run(debug=True, port=5000)