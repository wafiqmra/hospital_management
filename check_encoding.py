import chardet

with open("doctor_schedule.csv", "rb") as f:
    result = chardet.detect(f.read(10000))  # baca sebagian
    print(result)
