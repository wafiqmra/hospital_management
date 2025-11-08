from flask import Flask, render_template, request, send_file
import pandas as pd
import plotly.express as px
import plotly.io as pio
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
# ROUTE DASHBOARD
# ------------------------------
@app.route('/')
def index():
    # --- Load data dari database ---
    df_doctor = load_doctor_data()
    df_room, total_rooms, occupied_rooms, available_rooms, room_stats = load_room_data()
    df_patient, total_patients, gender_dist, payment_dist, insurance_dist, city_dist = load_patient_data()

    # --- Filter dokter berdasarkan input ---
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

    # --- Statistik dokter ---
    total_doctors = filtered_doctor_df['doctor_id'].nunique()
    total_schedules = len(filtered_doctor_df)
    total_specializations = filtered_doctor_df['specialization'].nunique()
    total_doctor_rooms = filtered_doctor_df['room_id'].nunique()

    # --- Chart spesialisasi ---
    if not filtered_doctor_df.empty:
        spec_count = filtered_doctor_df['specialization'].value_counts()
        fig_spec = px.pie(values=spec_count.values, names=spec_count.index, title="Distribution by Specialization")
        chart_spec = pio.to_html(fig_spec, full_html=False)
    else:
        chart_spec = "<p>No data available</p>"

    # --- Dropdown filter ---
    specializations = ['All'] + sorted(df_doctor['specialization'].dropna().unique().tolist())
    days = ['All'] + sorted(df_doctor['schedule_day'].dropna().unique().tolist())

    # --- Tabel data ---
    table_data = filtered_doctor_df[['name', 'specialization', 'schedule_day', 'start_time', 'end_time', 'room_id']].to_dict('records')
    room_table_data = df_room.to_dict('records')
    patient_table_data = df_patient[['patient_id', 'name', 'gender', 'age', 'city', 'payment_type', 'insurance_provider']].to_dict('records')

    # ✅ perbaikan baris ini
    patient_table_count = len(df_patient)

    # --- Chart Heatmap: Distribusi Jadwal berdasarkan Hari dan Spesialisasi ---
    if not filtered_doctor_df.empty:
        heatmap_data = (
            filtered_doctor_df.groupby(['schedule_day', 'specialization'])
            .size()
            .reset_index(name='count')
        )

        # Bikin pivot table agar cocok buat heatmap (baris=Day, kolom=Spesialisasi)
        pivot = heatmap_data.pivot(index='schedule_day', columns='specialization', values='count').fillna(0)

        import plotly.graph_objects as go
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
    else:
        chart_heatmap = "<p>No schedule data available</p>"

            # --- Chart Most Used Room ---
    if not filtered_doctor_df.empty and 'room_id' in filtered_doctor_df.columns:
        room_usage = (
            filtered_doctor_df.groupby('room_id')
            .size()
            .reset_index(name='count')
            .sort_values(by='count', ascending=False)
            .head(10)  # top 10 room
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

        chart_room_usage = pio.to_html(fig_room, full_html=False)
    else:
        chart_room_usage = "<p>No room usage data available</p>"




    # --- Render ke template ---
    return render_template(
        'dashboard.html',
        total_doctors=total_doctors,
        total_schedules=total_schedules,
        total_specializations=total_specializations,
        total_doctor_rooms=total_doctor_rooms,
        total_rooms=total_rooms,
        occupied_rooms=occupied_rooms,
        available_rooms=available_rooms,
        total_patients=total_patients,
        gender_dist=gender_dist,
        chart_spec=chart_spec,
        specializations=specializations,
        days=days,
        current_specialization=specialization,
        current_day=day,
        search_doctor=search_doctor,
        table_data=table_data,
        table_count=len(table_data),
        room_table_data=room_table_data,
        room_table_count=len(room_table_data),
        patient_table_data=patient_table_data,
        room_stats=room_stats,
        payment_dist=payment_dist,
        patient_table_count=patient_table_count,
        chart_heatmap=chart_heatmap
    )

# ------------------------------
# JALANKAN APLIKASI
# ------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)
