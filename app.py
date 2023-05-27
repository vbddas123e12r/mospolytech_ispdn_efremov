from flask import Flask, request, render_template, session, redirect, send_file
from flaskext.mysql import MySQL
import pymysql
import gost
import json
import datetime, os
from dotenv import load_dotenv
load_dotenv()


mysql = MySQL()
basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'media')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['MYSQL_DATABASE_USER'] = os.getenv("MYSQL_DATABASE_USER")
app.config['MYSQL_DATABASE_PASSWORD'] = os.getenv("MYSQL_DATABASE_PASSWORD")
app.config['MYSQL_DATABASE_DB'] = os.getenv("MYSQL_DATABASE_DB")
app.config['MYSQL_DATABASE_HOST'] = os.getenv("MYSQL_DATABASE_HOST")
mysql.init_app(app)

@app.route('/', methods=('GET', 'POST',))
def admin():
    conn = mysql.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            st.StudentId, t.Name, st.LastName, st.FirstName, st.MiddleName, st.DateOfBirth, sc.Name, cl.Class
        FROM Student st
        JOIN Class cl ON
        cl.ClassId = st.ClassId
        JOIN School sc ON
        sc.SchoolId = cl.SchoolId
        JOIN Town t ON
        t.TownId = sc.TownId
    """)
    students = cursor.fetchall()

    if not session.get('user'):
        return redirect('/login')

    if request.method == "POST":
        successful = False
        students = request.form
        salt = request.form['salt']

        myObject = gost.Streebog(512)

        conn = mysql.connect()
        
        cursor = conn.cursor()
        try:
            hashes_dict = {}
            for key, value in students.items():
                if key == 'salt':
                    continue
                
                student_id = value

                cursor.execute(f"""
                    SELECT FirstName, MiddleName, LastName, DateOfBirth, ClassId FROM Student 
                    WHERE StudentId={student_id}""")

                student_info = cursor.fetchall()
                student_fullname = student_info[0][0] + student_info[0][1] + student_info[0][2]
                date_of_birth = student_info[0][3]

                hashBytes = f"{student_fullname}{date_of_birth}{salt}".encode('utf-8')
                hashedStudent = myObject.hash(hashBytes)
                hexString = "".join([format(b, "02X") for b in hashedStudent])

                with db_context() as conn2:
                    cursor2 = conn2.cursor()
                    
                    cursor2.execute(f"""
                        INSERT INTO Student_hash 
                        (StudentId, ClassId, Hash)
                        VALUES
                        ({student_id}, {student_info[0][4]}, '{hexString}') 
                        ON DUPLICATE KEY UPDATE 
                        Hash = VALUES(Hash)
                    """)
                    conn2.commit()

                hashes_dict[student_fullname] = hexString

            stamp = datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            file_path = 'media/hashes_%s.json'%stamp

            with open(file_path, 'w', encoding='utf-8') as fp:
                json.dump(hashes_dict, fp, ensure_ascii=False, indent=4)
        except Exception as e:
            print(e)
            successful = False

        successful = True
        cursor.execute("SELECT * from Student")
        students = cursor.fetchall()

        return render_template('admin.html', students=students, successful=successful, file_path=file_path)

    return render_template('admin.html', students=students)

@app.route('/download_hashes', methods=('GET', 'POST',))
def download():
    file_path = request.args.get('file_path')

    return send_file(file_path, as_attachment=True)

@app.route('/login', methods=('GET', 'POST',))
def login():
    conn = mysql.connect()
    cursor = conn.cursor()

    errors = None
    if request.method == "POST":
        login = request.form['login']
        password = request.form['password']

        if login == 'admin' and password == os.getenv("ADMIN_P"):
            session['user'] = login
            session['role'] = 'admin'
            return redirect('/')
        else:
            cursor.execute(f"""
                    SELECT ClassTeacher FROM Teacher 
                    WHERE Login='{login}' AND Password='{password}'
            """)
            existing_tutor = cursor.fetchall()
            if existing_tutor != []:
                session['user'] = existing_tutor[0][0]
                session['role'] = 'tutor'
                return redirect('/tutor')
            else:
                errors = 'Неверные учетные данные, проверьте правильность ввода'

    return render_template('login.html', errors=errors)

@app.route('/logout', methods=('GET', 'POST',))
def logout():
    session.clear()
    return redirect('/login')

@app.route('/search', methods=('POST',))
def search():
    students = []

    student_firstname = request.form['student_firstname']
    student_middlename = request.form['student_middlename']
    student_lastname = request.form['student_lastname']
    date_of_birth = request.form['student_dateofbirth']
    student_town = request.form['student_town']
    student_school = request.form['student_school']
    student_class = request.form['student_class']
    salt = request.form['salt']
    
    with db_context() as conn2:
        cursor2 = conn2.cursor()
        myObject = gost.Streebog(512)

        cursor2.execute("SELECT TownId, Name FROM Town")
        towns = cursor2.fetchall()
        cursor2.execute("SELECT SchoolId, Name FROM School")
        schools = cursor2.fetchall()
        cursor2.execute("SELECT ClassId, Class FROM Class")
        classes = cursor2.fetchall()

        student_fullname = student_firstname + student_middlename + student_lastname

        hashBytes = f"{student_fullname}{date_of_birth}{salt}".encode('utf-8')
        hashedStudent = myObject.hash(hashBytes)
        hexString = "".join([format(b, "02X") for b in hashedStudent])
        cursor2.execute(f"""
            SELECT sth.StudentId, stdob.DateOfBirth, sth.Hash FROM Student_hash sth
            JOIN Student_dob stdob ON 
            stdob.StudentId = sth.StudentId
            JOIN Class cl ON
            cl.ClassId = sth.ClassId
            JOIN School sc ON
            sc.SchoolId = cl.SchoolId
            JOIN Town t ON
            t.TownId = sc.TownId
            WHERE sth.Hash = '{hexString}' AND t.TownId = '{student_town}' 
            AND sc.SchoolId = '{student_school}' AND cl.ClassId = '{student_class}'
        """)
        students = cursor2.fetchall()

    return render_template('tutor.html', students=students, student_firstname=student_firstname, 
                        student_middlename=student_middlename, student_lastname=student_lastname, 
                        date_of_birth=date_of_birth, student_town=student_town, 
                        student_school=student_school, student_class=student_class,
                        towns=towns, schools=schools, classes=classes,
                        salt=salt)

@app.route('/tutor', methods=('GET', 'POST',))
def tutor():
    students = []
    with db_context() as conn2:
        cursor2 = conn2.cursor()
        cursor2.execute(f"""
            SELECT 
                sth.StudentId, stdob.DateOfBirth, sth.Hash, tw.Name, sc.Name, cl.Class
            FROM Student_hash sth
            JOIN Student_dob stdob ON 
            stdob.StudentId = sth.StudentId
            JOIN Class cl ON
            cl.ClassId = sth.ClassId
            JOIN Teacher t ON
            t.ClassId = cl.ClassId
            JOIN School sc ON
            cl.SchoolId = sc.SchoolId
            JOIN Town tw ON
            tw.TownId = sc.TownId
            WHERE t.ClassTeacher = '{session['user']}'
        """)
        students = cursor2.fetchall()

        cursor2.execute("SELECT TownId, Name FROM Town")
        towns = cursor2.fetchall()
        cursor2.execute("SELECT SchoolId, Name FROM School")
        schools = cursor2.fetchall()
        cursor2.execute("SELECT ClassId, Class FROM Class")
        classes = cursor2.fetchall()

    return render_template('tutor.html', students=students, towns=towns, schools=schools, classes=classes,)

@app.route('/attendance', methods=('GET', 'POST',))
def attendance():
    semester = 1
    day_filter = ""
    semester_filter = ""
    salt = ""
    student_firstname = ""
    student_middlename = ""
    student_lastname = ""
    date_of_birth = ""

    if request.args.get('week'):
        week = request.args.get('week')
        semester = request.args.get('semester')
        semester_filter = f" AND Semester = {semester}"
        day = request.args.get('day')
        day_filter = f"AND att.Date = '{day}'"

        student_firstname = request.args.get('student_firstname')
        student_middlename = request.args.get('student_middlename')
        student_lastname = request.args.get('student_lastname')
        date_of_birth = request.args.get('student_dateofbirth')
        salt = request.args.get('salt')
    else:
        week = "(SELECT MAX(WeekId) FROM Attendance)"

    weeks = []
    students = []

    with db_context() as conn2:
        cursor2 = conn2.cursor()

        cursor2.execute(f"""
            SELECT DISTINCT Date from Attendance
        """)
        days = cursor2.fetchall()

        cursor2.execute(f"""
            SELECT WeekNumber FROM Week WHERE Semester = {semester}
        """)
        weeks = cursor2.fetchall()
        
        query = """
            SELECT 
                sth.Hash, att.Date, att.Status, sth.StudentId, 
                tw.Name, cl.Class, sc.Name
            FROM Attendance att
            join Student_hash sth ON
            sth.StudentId = att.StudentId
            JOIN Class cl ON
            cl.ClassId = sth.ClassId
            JOIN Teacher t ON
            t.ClassId = cl.ClassId
            JOIN School sc ON
            cl.SchoolId = sc.SchoolId
            JOIN Town tw ON
            tw.TownId = sc.TownId
            join Week w ON
            w.WeekId = att.WeekId
            where w.WeekNumber =
        """

        if salt != "":
            myObject = gost.Streebog(512)
            student_fullname = student_firstname + student_middlename + student_lastname
            hashBytes = f"{student_fullname}{date_of_birth}{salt}".encode('utf-8')
            hashedStudent = myObject.hash(hashBytes)
            hexString = "".join([format(b, "02X") for b in hashedStudent])

            cursor2.execute(f"""
                {query} {week} {day_filter} {semester_filter} AND t.ClassTeacher = '{session['user']}' 
                AND sth.Hash = '{hexString}'
            """)
        else:
            cursor2.execute(f"""{query} {week} {day_filter} {semester_filter} AND t.ClassTeacher = '{session['user']}'
            """)
        students = cursor2.fetchall()

    return render_template('attendance.html', 
        students=students, weeks=weeks, days=days, 
        student_firstname=student_firstname,
        student_middlename=student_middlename,
        student_lastname=student_lastname,
        date_of_birth=date_of_birth,
        salt=salt,
    )

@app.route('/set_attendance', methods=('GET', 'POST',))
def set_attendance():
    student_id = request.args.get('student')
    status = request.args.get('status')

    with db_context() as conn2:
        cursor2 = conn2.cursor()
        cursor2.execute(f"""
            UPDATE Attendance SET 
            Status='{status}' WHERE Attendance.StudentId={student_id}
        """)
        conn2.commit()

    return redirect('/attendance')

def db_context():
    return pymysql.connect(
        host = os.getenv("MYSQL_DATABASE_HOST2"),
        user = os.getenv("MYSQL_DATABASE_USER2"),
        password = os.getenv("MYSQL_DATABASE_PASSWORD2"),
        database = os.getenv("MYSQL_DATABASE_DB2"),
    )