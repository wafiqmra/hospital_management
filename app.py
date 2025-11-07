from flask import Flask, render_template, request, send_file
import pandas as pd
import plotly.express as px
import plotly.io as pio
import json
from datetime import datetime
import io

app = Flask(__name__)

# Fungsi load data dokter
def load_doctor_data():
    try:
        df = pd.read_csv('doctor_schedule.csv')

        # Pastikan kolom penting ada
        required_cols = ['doctor_id', 'name', 'specialization', 'schedule_day', 'start_time', 'end_time', 'room_id']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing column: {col}")

        # Konversi waktu ke tipe time
        df['start_time'] = pd.to_datetime(df['start_time'], format='%H:%M').dt.time
        df['end_time'] = pd.to_datetime(df['end_time'], format='%H:%M').dt.time

        # Durasi jam
        df['duration_hours'] = df.apply(
            lambda row: (datetime.combine(datetime.today(), row['end_time']) -
                        datetime.combine(datetime.today(), row['start_time'])).seconds / 3600,
            axis=1
        )

        return df

    except Exception as e:
        print(f"[ERROR] Gagal load data dokter: {e}")
        return pd.DataFrame()

# Fungsi load data ruangan
def load_room_data():
    try:
        df = pd.read_csv('rooms.csv')
        
        # Hitung statistik ruangan
        total_rooms = len(df)
        occupied_rooms = len(df[df['current_occupancy'] > 0])
        available_rooms = total_rooms - occupied_rooms
        
        # Hitung occupancy rate per tipe ruangan
        room_types = df['room_type'].unique()
        room_stats = {}
        
        for room_type in room_types:
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

# Fungsi load data pasien
def load_patient_data():
    try:
        df = pd.read_csv('patients.csv')
        
        # Konversi tanggal lahir
        df['birth_date'] = pd.to_datetime(df['birth_date'])
        
        # Hitung usia
        today = datetime.today()
        df['age'] = df['birth_date'].apply(lambda x: today.year - x.year - ((today.month, today.day) < (x.month, x.day)))
        
        # Kategorisasi usia
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
        
        # Statistik pasien
        total_patients = len(df)
        gender_dist = df['gender'].value_counts().to_dict()
        
        # Distribusi tipe pembayaran
        payment_dist = df['payment_type'].value_counts().to_dict()
        
        # Distribusi provider asuransi
        insurance_dist = df['insurance_provider'].value_counts().to_dict()
        
        # Distribusi kota
        city_dist = df['city'].value_counts().head(10).to_dict()
        
        return df, total_patients, gender_dist, payment_dist, insurance_dist, city_dist

    except Exception as e:
        print(f"[ERROR] Gagal load data pasien: {e}")
        return pd.DataFrame(), 0, {}, {}, {}, {}

@app.route('/')
def index():
    df_doctor = load_doctor_data()
    df_room, total_rooms, occupied_rooms, available_rooms, room_stats = load_room_data()
    df_patient, total_patients, gender_dist, payment_dist, insurance_dist, city_dist = load_patient_data()

    # Filter untuk data dokter
    specialization = request.args.get('specialization', 'All')
    day = request.args.get('day', 'All')
    search_doctor = request.args.get('search_doctor', '')

    # Filter data dokter
    filtered_doctor_df = df_doctor.copy()
    if specialization != 'All':
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['specialization'] == specialization]
    if day != 'All':
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['schedule_day'] == day]
    if search_doctor:
        filtered_doctor_df = filtered_doctor_df[filtered_doctor_df['name'].str.contains(search_doctor, case=False, na=False)]

    # Metrics ringkasan dokter
    total_doctors = filtered_doctor_df['doctor_id'].nunique()
    total_schedules = len(filtered_doctor_df)
    total_specializations = filtered_doctor_df['specialization'].nunique()
    total_doctor_rooms = filtered_doctor_df['room_id'].nunique()

    # Charts untuk dokter
    if not filtered_doctor_df.empty:
        # Chart 1: Distribusi Spesialisasi
        spec_count = filtered_doctor_df['specialization'].value_counts()
        fig_spec = px.pie(
            values=spec_count.values,
            names=spec_count.index,
            title="Distribution by Specialization"
        )
        chart_spec = pio.to_html(fig_spec, full_html=False)

        # Chart 2: Jumlah jadwal per hari
        day_count = filtered_doctor_df['schedule_day'].value_counts()
        fig_day = px.bar(
            x=day_count.index,
            y=day_count.values,
            title="Schedules per Day",
            labels={'x': 'Day', 'y': 'Number of Schedules'}
        )
        chart_day = pio.to_html(fig_day, full_html=False)

        # Chart 3: Heatmap (Hari x Spesialisasi)
        heatmap_data = filtered_doctor_df.groupby(['schedule_day', 'specialization']).size().unstack(fill_value=0)
        fig_heatmap = px.imshow(
            heatmap_data,
            title="Schedule Density Heatmap",
            labels=dict(x="Specialization", y="Day", color="Number of Schedules"),
            aspect="auto"
        )
        chart_heatmap = pio.to_html(fig_heatmap, full_html=False)

        # Chart 4: Penggunaan Ruangan
        room_usage = filtered_doctor_df['room_id'].value_counts().head(10)
        fig_rooms = px.bar(
            x=room_usage.index,
            y=room_usage.values,
            title="Top 10 Most Used Rooms",
            labels={'x': 'Room ID', 'y': 'Number of Schedules'}
        )
        chart_rooms = pio.to_html(fig_rooms, full_html=False)
    else:
        chart_spec = chart_day = chart_heatmap = chart_rooms = "<p>No data available</p>"

    # Charts untuk ruangan
    if not df_room.empty:
        # Chart 5: Distribusi Tipe Ruangan
        room_type_count = df_room['room_type'].value_counts()
        fig_room_type = px.pie(
            values=room_type_count.values,
            names=room_type_count.index,
            title="Room Type Distribution"
        )
        chart_room_type = pio.to_html(fig_room_type, full_html=False)

        # Chart 6: Occupancy Rate per Tipe Ruangan
        occupancy_data = []
        for room_type, stats in room_stats.items():
            occupancy_data.append({
                'room_type': room_type,
                'occupancy_rate': stats['occupancy_rate'],
                'occupied': stats['occupied'],
                'total': stats['total']
            })
        
        occupancy_df = pd.DataFrame(occupancy_data)
        fig_occupancy = px.bar(
            occupancy_df,
            x='room_type',
            y='occupancy_rate',
            title="Occupancy Rate by Room Type (%)",
            labels={'room_type': 'Room Type', 'occupancy_rate': 'Occupancy Rate (%)'},
            text='occupancy_rate'
        )
        fig_occupancy.update_traces(texttemplate='%{text}%', textposition='outside')
        chart_occupancy = pio.to_html(fig_occupancy, full_html=False)

    else:
        chart_room_type = chart_occupancy = "<p>No room data available</p>"

    # Charts untuk pasien
    if not df_patient.empty:
        # Chart 7: Distribusi Gender Pasien
        gender_count = df_patient['gender'].value_counts()
        fig_gender = px.pie(
            values=gender_count.values,
            names=gender_count.index,
            title="Patient Gender Distribution"
        )
        chart_gender = pio.to_html(fig_gender, full_html=False)

        # Chart 8: Distribusi Kelompok Usia
        age_group_count = df_patient['age_group'].value_counts()
        fig_age = px.bar(
            x=age_group_count.index,
            y=age_group_count.values,
            title="Patient Age Group Distribution",
            labels={'x': 'Age Group', 'y': 'Number of Patients'}
        )
        chart_age = pio.to_html(fig_age, full_html=False)

        # Chart 9: Distribusi Tipe Pembayaran
        payment_count = df_patient['payment_type'].value_counts()
        fig_payment = px.pie(
            values=payment_count.values,
            names=payment_count.index,
            title="Payment Type Distribution"
        )
        chart_payment = pio.to_html(fig_payment, full_html=False)

        # Chart 10: Distribusi Provider Asuransi
        insurance_count = df_patient['insurance_provider'].value_counts().head(10)
        fig_insurance = px.bar(
            x=insurance_count.index,
            y=insurance_count.values,
            title="Top 10 Insurance Providers",
            labels={'x': 'Insurance Provider', 'y': 'Number of Patients'}
        )
        chart_insurance = pio.to_html(fig_insurance, full_html=False)

        # Chart 11: Distribusi Kota
        city_count = df_patient['city'].value_counts().head(10)
        fig_city = px.bar(
            x=city_count.index,
            y=city_count.values,
            title="Top 10 Cities by Patient Count",
            labels={'x': 'City', 'y': 'Number of Patients'}
        )
        chart_city = pio.to_html(fig_city, full_html=False)

    else:
        chart_gender = chart_age = chart_payment = chart_insurance = chart_city = "<p>No patient data available</p>"

    # Daftar untuk filter dropdown
    specializations = ['All'] + sorted(df_doctor['specialization'].dropna().unique().tolist())
    days = ['All'] + sorted(df_doctor['schedule_day'].dropna().unique().tolist())

    # Tabel data
    table_data = filtered_doctor_df[['name', 'specialization', 'schedule_day', 'start_time', 'end_time', 'room_id']].to_dict('records')
    room_table_data = df_room.to_dict('records')
    patient_table_data = df_patient[['patient_id', 'name', 'gender', 'age', 'city', 'payment_type', 'insurance_provider']].to_dict('records')

    return render_template(
        'dashboard.html',
        # Metrics dokter
        total_doctors=total_doctors,
        total_schedules=total_schedules,
        total_specializations=total_specializations,
        total_doctor_rooms=total_doctor_rooms,
        
        # Metrics ruangan
        total_rooms=total_rooms,
        occupied_rooms=occupied_rooms,
        available_rooms=available_rooms,
        room_stats=room_stats,
        
        # Metrics pasien
        total_patients=total_patients,
        gender_dist=gender_dist,
        payment_dist=payment_dist,
        insurance_dist=insurance_dist,
        city_dist=city_dist,
        
        # Charts dokter
        chart_spec=chart_spec,
        chart_day=chart_day,
        chart_heatmap=chart_heatmap,
        chart_rooms=chart_rooms,
        
        # Charts ruangan
        chart_room_type=chart_room_type,
        chart_occupancy=chart_occupancy,
        
        # Charts pasien
        chart_gender=chart_gender,
        chart_age=chart_age,
        chart_payment=chart_payment,
        chart_insurance=chart_insurance,
        chart_city=chart_city,
        
        # Filter data
        specializations=specializations,
        days=days,
        current_specialization=specialization,
        current_day=day,
        search_doctor=search_doctor,
        
        # Tabel data
        table_data=table_data,
        table_count=len(table_data),
        room_table_data=room_table_data,
        room_table_count=len(room_table_data),
        patient_table_data=patient_table_data,
        patient_table_count=len(patient_table_data)
    )

@app.route('/export')
def export_data():
    df = load_doctor_data()
    if df.empty:
        return "Data tidak ditemukan.", 404

    specialization = request.args.get('specialization', 'All')
    day = request.args.get('day', 'All')
    search_doctor = request.args.get('search_doctor', '')

    # Filter data
    filtered_df = df.copy()
    if specialization != 'All':
        filtered_df = filtered_df[filtered_df['specialization'] == specialization]
    if day != 'All':
        filtered_df = filtered_df[filtered_df['schedule_day'] == day]
    if search_doctor:
        filtered_df = filtered_df[filtered_df['name'].str.contains(search_doctor, case=False, na=False)]

    # Simpan CSV ke memori
    output = io.StringIO()
    filtered_df.to_csv(output, index=False)
    output.seek(0)

    filename = "doctor_schedules"
    if specialization != 'All':
        filename += f"_{specialization}"
    if day != 'All':
        filename += f"_{day}"
    filename += ".csv"

    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/export_rooms')
def export_rooms():
    df_room, _, _, _, _ = load_room_data()
    if df_room.empty:
        return "Data ruangan tidak ditemukan.", 404

    # Simpan CSV ke memori
    output = io.StringIO()
    df_room.to_csv(output, index=False)
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name="rooms_data.csv"
    )

@app.route('/export_patients')
def export_patients():
    df_patient, _, _, _, _, _ = load_patient_data()
    if df_patient.empty:
        return "Data pasien tidak ditemukan.", 404

    # Simpan CSV ke memori
    output = io.StringIO()
    df_patient.to_csv(output, index=False)
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name="patients_data.csv"
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)