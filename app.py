from flask import Flask, render_template, request, send_file
import pandas as pd
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
import mysql.connector
from datetime import datetime
import io

app = Flask(__name__)

# ------------------------------
# FUNGSI KONEKSI DATABASE
# ------------------------------
def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",          # ubah jika pakai user lain
        password="",          # kosong kalau default Laragon
        database="hospital"   # nama database kamu
    )

# ------------------------------
# LOAD DATA DOKTER
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

# ------------------------------
# LOAD DATA RUANGAN
# ------------------------------
def load_room_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM rooms"
        df = pd.read_sql(query, conn)
        conn.close()

        total_rooms = len(df)
        occupied_rooms = len(df[df['current_occupancy'] > 0])
        available_rooms = total_rooms - occupied_rooms

        room_stats = {}
        for room_type in df['room_type'].unique():
            type_data = df[df['room_type'] == room_type]
            total_type = len(type_data)
            occupied_type = len(type_data[type_data['current_occupancy'] > 0])
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

# ------------------------------
# LOAD DATA PASIEN
# ------------------------------
def load_patient_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM patients"
        df = pd.read_sql(query, conn)
        conn.close()

        df['birth_date'] = pd.to_datetime(df['birth_date'])
        today = datetime.today()
        df['age'] = df['birth_date'].apply(lambda x: today.year - x.year - ((today.month, today.day) < (x.month, x.day)))

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
        gender_dist = df['gender'].value_counts().to_dict()
        payment_dist = df['payment_type'].value_counts().to_dict()
        insurance_dist = df['insurance_provider'].value_counts().to_dict()
        city_dist = df['city'].value_counts().head(10).to_dict()

        return df, total_patients, gender_dist, payment_dist, insurance_dist, city_dist

    except Exception as e:
        print(f"[ERROR] Gagal load data pasien: {e}")
        return pd.DataFrame(), 0, {}, {}, {}, {}

# ------------------------------
# LOAD DATA PHARMACY
# ------------------------------
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
        df['current_stock'] = df['stock_in'] - df['stock_out']

        # Statistik
        total_medicines = len(df)
        low_stock_medicines = len(df[df['current_stock'] <= 5])
        out_of_stock_medicines = len(df[df['current_stock'] <= 0])
        pharmacy_categories = df['category'].nunique()

        return df, total_medicines, low_stock_medicines, out_of_stock_medicines, pharmacy_categories

    except Exception as e:
        print(f"[ERROR] Gagal load data pharmacy: {e}")
        return pd.DataFrame(columns=[
            'drug_id','drug_name','category','stock_in','stock_out','stock_date','expiry_date','supplier'
        ]), 0, 0, 0, 0

# ------------------------------
# LOAD DATA STAFF
# ------------------------------
def load_staff_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM staff"
        df = pd.read_sql(query, conn)
        conn.close()

        # Hitung years of service
        df['hire_date'] = pd.to_datetime(df['hire_date'])
        today = datetime.today()
        df['years_of_service'] = ((today - df['hire_date']).dt.days / 365.25).round(1)

        # Hitung statistik
        total_staff = len(df)
        active_staff = len(df[df['active'] == 'True'])
        inactive_staff = total_staff - active_staff
        staff_departments_count = df['department'].nunique()

        return df, total_staff, active_staff, inactive_staff, staff_departments_count

    except Exception as e:
        print(f"[ERROR] Gagal load data staff: {e}")
        return pd.DataFrame(columns=[
            'staff_id', 'name', 'role', 'department', 'hire_date', 'active', 'years_of_service'
        ]), 0, 0, 0, 0

# ------------------------------
# LOAD DATA LAB TESTS
# ------------------------------
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
        pending_tests = len(df[df['result_status'] == 'Pending'])
        completed_tests = len(df[df['result_status'] == 'Completed'])
        lab_test_types_count = df['test_type'].nunique()

        return df, total_lab_tests, pending_tests, completed_tests, lab_test_types_count

    except Exception as e:
        print(f"[ERROR] Gagal load data lab tests: {e}")
        return pd.DataFrame(columns=[
            'test_id', 'patient_id', 'patient_name', 'test_type', 
            'scheduled_date', 'result_date', 'result_status', 'lab_staff_id'
        ]), 0, 0, 0, 0

# ------------------------------
# ROUTES UNTUK SETIAP TAB
# ------------------------------

@app.route('/')
def index():
    # Default redirect ke doctor tab
    return dashboard()

@app.route('/doctor')
def doctor_tab():
    # Load data dokter
    df_doctor = load_doctor_data()

    # Filter dokter berdasarkan input
    specialization = request.args.get('specialization', 'All')
    day = request.args.get('day', 'All')
    search_doctor = request.args.get('search_doctor', '')

    filtered_doctor_df = df_doctor.copy()
    if specialization != 'All':
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['specialization'] == specialization]
    if day != 'All':
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['schedule_day'] == day]
    if search_doctor:
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['name'].str.contains(search_doctor, case=False, na=False)]

    # Statistik dokter
    total_doctors = filtered_doctor_df['doctor_id'].nunique()
    total_schedules = len(filtered_doctor_df)
    total_specializations = filtered_doctor_df['specialization'].nunique()
    total_doctor_rooms = filtered_doctor_df['room_id'].nunique()

    # Chart spesialisasi
    if not filtered_doctor_df.empty:
        spec_count = filtered_doctor_df['specialization'].value_counts()
        fig_spec = px.pie(values=spec_count.values, names=spec_count.index, title="Distribution by Specialization")
        chart_spec = pio.to_html(fig_spec, full_html=False)
        
        # Chart hari
        day_count = filtered_doctor_df['schedule_day'].value_counts()
        fig_day = px.bar(x=day_count.index, y=day_count.values, title="Schedules by Day")
        chart_day = pio.to_html(fig_day, full_html=False)
        
        # Chart heatmap
        heatmap_data = (
            filtered_doctor_df.groupby(['schedule_day', 'specialization'])
            .size()
            .reset_index(name='count')
        )
        pivot = heatmap_data.pivot(index='schedule_day', columns='specialization', values='count').fillna(0)
        fig_heatmap = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale='Plasma',
            colorbar=dict(title="Number of Schedules")
        ))
        fig_heatmap.update_layout(
            title="Schedule Density Heatmap",
            xaxis_title="Specialization",
            yaxis_title="Day",
            template="plotly_white"
        )
        chart_heatmap = pio.to_html(fig_heatmap, full_html=False)
        
        # Chart room usage
        room_usage = (
            filtered_doctor_df.groupby('room_id')
            .size()
            .reset_index(name='count')
            .sort_values(by='count', ascending=False)
            .head(10)
        )
        fig_room = px.bar(
            room_usage,
            x='room_id',
            y='count',
            text='count',
            color='count',
            color_continuous_scale='Blues',
            title="Top 10 Most Used Rooms"
        )
        fig_room.update_traces(textposition='outside')
        fig_room.update_layout(
            xaxis_title="Room ID",
            yaxis_title="Usage Count",
            template="plotly_white"
        )
        chart_rooms = pio.to_html(fig_room, full_html=False)
    else:
        chart_spec = "<p>No data available</p>"
        chart_day = "<p>No data available</p>"
        chart_heatmap = "<p>No data available</p>"
        chart_rooms = "<p>No data available</p>"

    # Dropdown filter
    specializations = ['All'] + sorted(df_doctor['specialization'].dropna().unique().tolist())
    days = ['All'] + sorted(df_doctor['schedule_day'].dropna().unique().tolist())

    # Tabel data
    table_data = filtered_doctor_df[['name', 'specialization', 'schedule_day', 'start_time', 'end_time', 'room_id']].to_dict('records')

    return render_template(
        'doctor_tab.html',
        total_doctors=total_doctors,
        total_schedules=total_schedules,
        total_specializations=total_specializations,
        total_doctor_rooms=total_doctor_rooms,
        chart_spec=chart_spec,
        chart_day=chart_day,
        chart_heatmap=chart_heatmap,
        chart_rooms=chart_rooms,
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
    # Load data ruangan
    df_room, total_rooms, occupied_rooms, available_rooms, room_stats = load_room_data()

    # Chart room type distribution
    if not df_room.empty and 'room_type' in df_room.columns:
        room_type_count = df_room['room_type'].value_counts()
        fig_room_type = px.pie(
            values=room_type_count.values,
            names=room_type_count.index,
            title="Room Type Distribution"
        )
        chart_room_type = pio.to_html(fig_room_type, full_html=False)
    else:
        chart_room_type = "<p>No room type data available</p>"

    # Chart occupancy rate by room type
    if room_stats:
        room_type = list(room_stats.keys())
        occupancy_rate = [v['occupancy_rate'] for v in room_stats.values()]
        fig_occ_rate = px.bar(
            x=room_type,
            y=occupancy_rate,
            text=[f"{r:.1f}%" for r in occupancy_rate],
            title="Occupancy Rate by Room Type (%)"
        )
        fig_occ_rate.update_traces(textposition='outside', marker_color='royalblue')
        fig_occ_rate.update_layout(
            xaxis_title="Room Type",
            yaxis_title="Occupancy Rate (%)",
            yaxis=dict(range=[0, 100]),
            template="plotly_white"
        )
        chart_occupancy = pio.to_html(fig_occ_rate, full_html=False)
    else:
        chart_occupancy = "<p>No occupancy data available</p>"

    # Tabel data
    room_table_data = df_room.to_dict('records')

    return render_template(
        'room_tab.html',
        total_rooms=total_rooms,
        occupied_rooms=occupied_rooms,
        available_rooms=available_rooms,
        room_stats=room_stats,
        chart_room_type=chart_room_type,
        chart_occupancy=chart_occupancy,
        room_table_data=room_table_data,
        room_table_count=len(room_table_data),
        now=datetime.now()
    )

@app.route('/patient')
def patient_tab():
    # Load data pasien
    df_patient, total_patients, gender_dist, payment_dist, insurance_dist, city_dist = load_patient_data()

    # Chart Patient Gender
    if gender_dist:
        fig_gender = px.pie(
            names=list(gender_dist.keys()),
            values=list(gender_dist.values()),
            title="Patient Gender Distribution"
        )
        chart_gender = pio.to_html(fig_gender, full_html=False)
    else:
        chart_gender = "<p>No gender data available</p>"

    # Chart Patient Age Group
    if not df_patient.empty:
        age_group_count = df_patient['age_group'].value_counts()
        fig_age = px.pie(
            names=age_group_count.index,
            values=age_group_count.values,
            title="Patient Age Group Distribution"
        )
        chart_age = pio.to_html(fig_age, full_html=False)
    else:
        chart_age = "<p>No age data available</p>"

    # Chart Payment Type
    if payment_dist:
        fig_payment = px.pie(
            names=list(payment_dist.keys()),
            values=list(payment_dist.values()),
            title="Payment Type Distribution"
        )
        chart_payment = pio.to_html(fig_payment, full_html=False)
    else:
        chart_payment = "<p>No payment type data available</p>"

    # Chart Insurance Provider
    if insurance_dist:
        fig_insurance = px.pie(
            names=list(insurance_dist.keys()),
            values=list(insurance_dist.values()),
            title="Insurance Provider Distribution"
        )
        chart_insurance = pio.to_html(fig_insurance, full_html=False)
    else:
        chart_insurance = "<p>No insurance data available</p>"

    # Chart Top 10 Cities
    if city_dist:
        fig_city = px.pie(
            names=list(city_dist.keys()),
            values=list(city_dist.values()),
            title="Top 10 Cities by Patient Count"
        )
        chart_city = pio.to_html(fig_city, full_html=False)
    else:
        chart_city = "<p>No city data available</p>"

    # Tabel data
    patient_table_data = df_patient[['patient_id', 'name', 'gender', 'age', 'city', 'payment_type', 'insurance_provider']].to_dict('records')

    return render_template(
        'patient_tab.html',
        total_patients=total_patients,
        gender_dist=gender_dist,
        payment_dist=payment_dist,
        chart_gender=chart_gender,
        chart_age=chart_age,
        chart_payment=chart_payment,
        chart_insurance=chart_insurance,
        chart_city=chart_city,
        patient_table_data=patient_table_data,
        patient_table_count=len(patient_table_data),
        now=datetime.now()
    )

@app.route('/pharmacy')
def pharmacy_tab():
    # Load data pharmacy
    df_pharmacy, total_medicines, low_stock_medicines, out_of_stock_medicines, pharmacy_categories = load_pharmacy_data()

    # Chart untuk Pharmacy
    if not df_pharmacy.empty:
        # Chart distribusi kategori obat
        category_count = df_pharmacy['category'].value_counts()
        fig_category = px.pie(values=category_count.values, names=category_count.index,
                            title="Medicine Distribution by Category")
        chart_medicine_category = pio.to_html(fig_category, full_html=False)
        
        # Chart status stok
        stock_status = {
            'In Stock': len(df_pharmacy[df_pharmacy['current_stock'] > 5]),
            'Low Stock': len(df_pharmacy[(df_pharmacy['current_stock'] <= 5) & (df_pharmacy['current_stock'] > 0)]),
            'Out of Stock': len(df_pharmacy[df_pharmacy['current_stock'] <= 0])
        }
        fig_stock = px.bar(x=list(stock_status.keys()), y=list(stock_status.values()),
                        title="Medicine Stock Status", color=list(stock_status.keys()),
                        color_discrete_map={'In Stock': '#4cc9f0', 'Low Stock': '#f72585', 'Out of Stock': '#e63946'})
        chart_stock_status = pio.to_html(fig_stock, full_html=False)

        # Chart obat yang akan kadaluarsa
        df_pharmacy['expiry_date'] = pd.to_datetime(df_pharmacy['expiry_date'])
        upcoming_expiry = df_pharmacy[df_pharmacy['expiry_date'] <= (datetime.today() + pd.Timedelta(days=30))]
        if not upcoming_expiry.empty:
            fig_expiry = px.bar(upcoming_expiry, x='drug_name', y='current_stock',
                                title="Medicines Expiring in 30 Days", color='current_stock')
            chart_expiry = pio.to_html(fig_expiry, full_html=False)
        else:
            chart_expiry = "<p>No medicines expiring soon</p>"
        
        # Chart supplier
        supplier_count = df_pharmacy['supplier'].value_counts().head(10)
        if not supplier_count.empty:
            fig_supplier = px.bar(x=supplier_count.index, y=supplier_count.values,
                                title="Top 10 Suppliers", color=supplier_count.values)
            chart_supplier = pio.to_html(fig_supplier, full_html=False)
        else:
            chart_supplier = "<p>No supplier data available</p>"
    else:
        chart_medicine_category = "<p>No pharmacy data available</p>"
        chart_stock_status = "<p>No pharmacy data available</p>"
        chart_expiry = "<p>No pharmacy data available</p>"
        chart_supplier = "<p>No supplier data available</p>"

    # Tabel data pharmacy
    pharmacy_table_data = df_pharmacy.to_dict('records')

    return render_template(
        'pharmacy_tab.html',
        total_medicines=total_medicines,
        low_stock_medicines=low_stock_medicines,
        out_of_stock_medicines=out_of_stock_medicines,
        pharmacy_categories=pharmacy_categories,
        chart_medicine_category=chart_medicine_category,
        chart_stock_status=chart_stock_status,
        chart_expiry=chart_expiry,
        chart_supplier=chart_supplier,
        pharmacy_table_data=pharmacy_table_data,
        pharmacy_table_count=len(pharmacy_table_data),
        now=datetime.now()
    )

@app.route('/dashboard')
def dashboard():
    """Dashboard utama dengan ringkasan hari ini"""
    try:
        today = datetime.today().date()
        
        # Data dokter hari ini
        df_doctor = load_doctor_data()
        today_doctors = df_doctor[df_doctor['schedule_day'] == today.strftime('%A')]
        total_today_doctors = len(today_doctors)
        
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
        today_lab_tests = df_lab[df_lab['scheduled_date'] == today.strftime('%Y-%m-%d')]
        total_today_tests = len(today_lab_tests)
        
        # Data staff aktif
        df_staff, total_staff, active_staff, inactive_staff, staff_departments_count = load_staff_data()
        
        # Statistik untuk cards
        stats = {
            'today_doctors': total_today_doctors,
            'today_patients': today_patients,
            'today_tests': total_today_tests,
            'occupied_rooms': occupied_rooms,
            'available_rooms': available_rooms,
            'occupancy_rate': round(occupancy_rate, 1),
            'low_stock_medicines': low_stock_medicines,
            'active_staff': active_staff,
            'pending_tests': pending_tests
        }
        
        # Data untuk charts dengan error handling
        try:
            # Chart distribusi dokter hari ini
            if not today_doctors.empty:
                spec_count = today_doctors['specialization'].value_counts()
                fig_today_doctors = px.pie(
                    values=spec_count.values, 
                    names=spec_count.index, 
                    title=f"Dokter Hari Ini ({today.strftime('%A')})"
                )
                chart_today_doctors = pio.to_html(fig_today_doctors, full_html=False)
            else:
                chart_today_doctors = "<p>Tidak ada jadwal dokter hari ini</p>"
            
            # Chart status ruangan
            room_status_data = {
                'Status': ['Terisi', 'Tersedia'],
                'Count': [occupied_rooms, available_rooms]
            }
            fig_room_status = px.pie(
                room_status_data, 
                values='Count', 
                names='Status',
                title="Status Ruangan",
                color='Status',
                color_discrete_map={'Terisi': '#e63946', 'Tersedia': '#4cc9f0'}
            )
            chart_room_status = pio.to_html(fig_room_status, full_html=False)
            
            # Chart status stok obat
            stock_status_data = {
                'Status': ['Stok Normal', 'Stok Rendah', 'Habis'],
                'Count': [
                    total_medicines - low_stock_medicines - out_of_stock_medicines,
                    low_stock_medicines,
                    out_of_stock_medicines
                ]
            }
            fig_stock_status = px.bar(
                stock_status_data,
                x='Status',
                y='Count',
                title="Status Stok Obat",
                color='Status',
                color_discrete_map={
                    'Stok Normal': '#4cc9f0', 
                    'Stok Rendah': '#f72585', 
                    'Habis': '#e63946'
                }
            )
            chart_stock_status = pio.to_html(fig_stock_status, full_html=False)
            
            # Chart tes lab hari ini
            if not today_lab_tests.empty:
                test_status_count = today_lab_tests['result_status'].value_counts()
                fig_today_tests = px.pie(
                    values=test_status_count.values,
                    names=test_status_count.index,
                    title="Tes Lab Hari Ini"
                )
                chart_today_tests = pio.to_html(fig_today_tests, full_html=False)
            else:
                chart_today_tests = "<p>Tidak ada tes lab hari ini</p>"
                
        except Exception as e:
            print(f"Error generating charts: {e}")
            chart_today_doctors = "<p>Error loading chart data</p>"
            chart_room_status = "<p>Error loading chart data</p>"
            chart_stock_status = "<p>Error loading chart data</p>"
            chart_today_tests = "<p>Error loading chart data</p>"

        return render_template(
            'dashboard.html',
            stats=stats,
            chart_today_doctors=chart_today_doctors,
            chart_room_status=chart_room_status,
            chart_stock_status=chart_stock_status,
            chart_today_tests=chart_today_tests,
            today=today,
            now=datetime.now()
        )
        
    except Exception as e:
        print(f"Dashboard error: {e}")
        return render_template(
            'dashboard.html',
            stats={},
            chart_today_doctors="<p>System error</p>",
            chart_room_status="<p>System error</p>",
            chart_stock_status="<p>System error</p>",
            chart_today_tests="<p>System error</p>",
            today=datetime.today().date(),
            now=datetime.now()
        )


@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.context_processor
def inject_request():
    return {'request': request}

@app.route('/lab')
def lab_tab():
    # Load data lab tests
    df_lab, total_lab_tests, pending_tests, completed_tests, lab_test_types_count = load_lab_tests_data()

    # Filter lab tests berdasarkan input
    test_type = request.args.get('test_type', 'All')
    result_status = request.args.get('result_status', 'All')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    filtered_lab_df = df_lab.copy()
    if test_type != 'All':
        filtered_lab_df = filtered_lab_df[filtered_lab_df['test_type'] == test_type]
    if result_status != 'All':
        filtered_lab_df = filtered_lab_df[filtered_lab_df['result_status'] == result_status]
    if start_date:
        filtered_lab_df = filtered_lab_df[filtered_lab_df['scheduled_date'] >= start_date]
    if end_date:
        filtered_lab_df = filtered_lab_df[filtered_lab_df['scheduled_date'] <= end_date]

    # Dropdown filter untuk lab tests
    lab_test_types = ['All'] + sorted(df_lab['test_type'].dropna().unique().tolist())
    lab_result_statuses = ['All'] + sorted(df_lab['result_status'].dropna().unique().tolist())

    # Chart untuk Lab Tests
    if not filtered_lab_df.empty:
        # Chart distribusi tipe test
        test_type_count = filtered_lab_df['test_type'].value_counts()
        fig_test_type = px.pie(values=test_type_count.values, names=test_type_count.index, 
                              title="Distribution by Test Type")
        chart_test_type = pio.to_html(fig_test_type, full_html=False)
        
        # Chart status hasil
        result_status_count = filtered_lab_df['result_status'].value_counts()
        fig_result_status = px.bar(x=result_status_count.index, y=result_status_count.values,
                                  title="Test Result Status", color=result_status_count.index,
                                  color_discrete_map={'Completed': '#4cc9f0', 'Pending': '#f72585', 'Cancelled': '#e63946'})
        chart_result_status = pio.to_html(fig_result_status, full_html=False)
        
        # Chart tes harian (trend)
        daily_tests = filtered_lab_df.groupby('scheduled_date').size().reset_index(name='count')
        if not daily_tests.empty:
            fig_daily = px.line(daily_tests, x='scheduled_date', y='count', 
                               title="Daily Tests Trend", markers=True)
            chart_daily_tests = pio.to_html(fig_daily, full_html=False)
        else:
            chart_daily_tests = "<p>No daily test data available</p>"

        # Chart distribusi lab staff
        lab_staff_count = filtered_lab_df['lab_staff_id'].value_counts().head(10)
        if not lab_staff_count.empty:
            fig_lab_staff = px.bar(x=lab_staff_count.index, y=lab_staff_count.values,
                                  title="Top 10 Lab Staff by Test Count", 
                                  labels={'x': 'Lab Staff ID', 'y': 'Number of Tests'})
            chart_lab_staff = pio.to_html(fig_lab_staff, full_html=False)
        else:
            chart_lab_staff = "<p>No lab staff data available</p>"
    else:
        chart_test_type = "<p>No lab test data available</p>"
        chart_result_status = "<p>No lab test data available</p>"
        chart_daily_tests = "<p>No lab test data available</p>"
        chart_lab_staff = "<p>No lab test data available</p>"

    # Tabel data lab tests
    lab_table_data = filtered_lab_df.to_dict('records')

    return render_template(
        'lab_tab.html',
        total_lab_tests=total_lab_tests,
        pending_tests=pending_tests,
        completed_tests=completed_tests,
        lab_test_types_count=lab_test_types_count,
        lab_table_data=lab_table_data,
        lab_table_count=len(lab_table_data),
        lab_test_types=lab_test_types,
        lab_result_statuses=lab_result_statuses,
        current_test_type=test_type,
        current_result_status=result_status,
        current_start_date=start_date,
        current_end_date=end_date,
        chart_test_type=chart_test_type,
        chart_result_status=chart_result_status,
        chart_daily_tests=chart_daily_tests,
        chart_lab_staff=chart_lab_staff,
        now=datetime.now()
    )

@app.route('/staff')
def staff_tab():
    # Load data staff
    df_staff, total_staff, active_staff, inactive_staff, staff_departments_count = load_staff_data()

    # Filter staff berdasarkan input
    staff_role = request.args.get('staff_role', 'All')
    staff_department = request.args.get('staff_department', 'All')
    staff_status = request.args.get('staff_status', 'All')
    search_staff = request.args.get('search_staff', '')

    filtered_staff_df = df_staff.copy()
    if staff_role != 'All':
        filtered_staff_df = filtered_staff_df[filtered_staff_df['role'] == staff_role]
    if staff_department != 'All':
        filtered_staff_df = filtered_staff_df[filtered_staff_df['department'] == staff_department]
    if staff_status != 'All':
        status_filter = 'True' if staff_status == 'Active' else 'False'
        filtered_staff_df = filtered_staff_df[filtered_staff_df['active'] == status_filter]
    if search_staff:
        filtered_staff_df = filtered_staff_df[filtered_staff_df['name'].str.contains(search_staff, case=False, na=False)]

    # Dropdown filter untuk staff
    staff_roles = ['All'] + sorted(df_staff['role'].dropna().unique().tolist())
    staff_departments = ['All'] + sorted(df_staff['department'].dropna().unique().tolist())
    staff_statuses = ['All', 'Active', 'Inactive']

    # Chart untuk Staff
    if not filtered_staff_df.empty:
        # Chart distribusi role
        role_count = filtered_staff_df['role'].value_counts()
        fig_role = px.pie(values=role_count.values, names=role_count.index, 
                         title="Staff Distribution by Role")
        chart_staff_role = pio.to_html(fig_role, full_html=False)
        
        # Chart distribusi department
        dept_count = filtered_staff_df['department'].value_counts()
        fig_dept = px.bar(x=dept_count.index, y=dept_count.values,
                         title="Staff by Department", color=dept_count.values,
                         color_continuous_scale='Viridis')
        chart_staff_department = pio.to_html(fig_dept, full_html=False)
        
        # Chart staff berdasarkan tahun hire
        filtered_staff_df['hire_year'] = filtered_staff_df['hire_date'].dt.year
        hire_year_count = filtered_staff_df['hire_year'].value_counts().sort_index()
        if not hire_year_count.empty:
            fig_hire_year = px.line(x=hire_year_count.index, y=hire_year_count.values,
                                   title="Staff Hiring Trend by Year", markers=True,
                                   labels={'x': 'Year', 'y': 'Number of Staff Hired'})
            chart_staff_hire_year = pio.to_html(fig_hire_year, full_html=False)
        else:
            chart_staff_hire_year = "<p>No hiring data available</p>"

        # Chart status staff
        active_count = len(filtered_staff_df[filtered_staff_df['active'] == 'True'])
        inactive_count = len(filtered_staff_df[filtered_staff_df['active'] == 'False'])
        fig_status = px.pie(
            values=[active_count, inactive_count],
            names=['Active', 'Inactive'],
            title="Staff Status Distribution",
            color=['Active', 'Inactive'],
            color_discrete_map={'Active': '#4cc9f0', 'Inactive': '#e63946'}
        )
        chart_staff_status = pio.to_html(fig_status, full_html=False)
    else:
        chart_staff_role = "<p>No staff data available</p>"
        chart_staff_department = "<p>No staff data available</p>"
        chart_staff_hire_year = "<p>No staff data available</p>"
        chart_staff_status = "<p>No staff data available</p>"

    # Tabel data staff
    staff_table_data = filtered_staff_df.to_dict('records')

    return render_template(
        'staff_tab.html',
        total_staff=total_staff,
        active_staff=active_staff,
        inactive_staff=inactive_staff,
        staff_departments_count=staff_departments_count,
        staff_table_data=staff_table_data,
        staff_table_count=len(staff_table_data),
        staff_roles=staff_roles,
        staff_departments=staff_departments,
        staff_statuses=staff_statuses,
        current_staff_role=staff_role,
        current_staff_department=staff_department,
        current_staff_status=staff_status,
        search_staff=search_staff,
        chart_staff_role=chart_staff_role,
        chart_staff_department=chart_staff_department,
        chart_staff_hire_year=chart_staff_hire_year,
        chart_staff_status=chart_staff_status,
        now=datetime.now()
    )

# ------------------------------
# EXPORT FUNCTIONS
# ------------------------------

@app.route('/export_pharmacy')
def export_pharmacy():
    try:
        df_pharmacy, _, _, _, _ = load_pharmacy_data()
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_pharmacy.to_excel(writer, sheet_name='Pharmacy_Inventory', index=False)
        
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='pharmacy_inventory.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    
    except Exception as e:
        return f"Error exporting pharmacy data: {str(e)}", 500

@app.route('/export_lab_tests')
def export_lab_tests():
    try:
        df_lab, _, _, _, _ = load_lab_tests_data()
        
        # Apply filters sama seperti di route utama
        test_type = request.args.get('test_type', 'All')
        result_status = request.args.get('result_status', 'All')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        filtered_df = df_lab.copy()
        if test_type != 'All':
            filtered_df = filtered_df[filtered_df['test_type'] == test_type]
        if result_status != 'All':
            filtered_df = filtered_df[filtered_df['result_status'] == result_status]
        if start_date:
            filtered_df = filtered_df[filtered_df['scheduled_date'] >= start_date]
        if end_date:
            filtered_df = filtered_df[filtered_df['scheduled_date'] <= end_date]
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            filtered_df.to_excel(writer, sheet_name='Lab_Tests', index=False)
        
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='lab_tests.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    
    except Exception as e:
        return f"Error exporting lab test data: {str(e)}", 500

@app.route('/export_staff')
def export_staff():
    try:
        df_staff, _, _, _, _ = load_staff_data()
        
        # Apply filters sama seperti di route utama
        staff_role = request.args.get('role', 'All')
        staff_department = request.args.get('department', 'All')
        staff_status = request.args.get('status', 'All')
        search_staff = request.args.get('search', '')
        
        filtered_df = df_staff.copy()
        if staff_role != 'All':
            filtered_df = filtered_df[filtered_df['role'] == staff_role]
        if staff_department != 'All':
            filtered_df = filtered_df[filtered_df['department'] == staff_department]
        if staff_status != 'All':
            status_filter = 'True' if staff_status == 'Active' else 'False'
            filtered_df = filtered_df[filtered_df['active'] == status_filter]
        if search_staff:
            filtered_df = filtered_df[filtered_df['name'].str.contains(search_staff, case=False, na=False)]
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            filtered_df.to_excel(writer, sheet_name='Staff_Data', index=False)
        
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='staff_data.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    
    except Exception as e:
        return f"Error exporting staff data: {str(e)}", 500

# ------------------------------
# JALANKAN APLIKASI
# ------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)