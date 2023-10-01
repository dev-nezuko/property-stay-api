Here's a `README.md` file tailored for your Django project, including the directory structure, installation instructions, and PostgreSQL database setup.

```markdown
# BnBU Backend API

A Django-based backend API for managing user accounts with custom user types.

## Directory Structure

```plaintext
bnbu_backend_api/
├── bnbu_backend_api/         # Main project directory
│   ├── __init__.py
│   ├── settings.py           # Project settings
│   ├── urls.py               # URL configurations
│   └── wsgi.py               # WSGI application
├── account/                   # User account app
│   ├── migrations/            # Database migrations
│   ├── __init__.py
│   ├── admin.py              # Admin interface configurations
│   ├── apps.py               # App configurations
│   ├── forms.py              # Custom forms for user creation
│   ├── models.py             # Custom user model
│   ├── tests.py              # Test cases
│   ├── urls.py               # URL patterns for account-related views
│   └── views.py              # Views for account management
├── templates/                 # HTML templates
│   └── accounts/              # Templates for account views
│       ├── dashboard.html
│       ├── login.html
│       ├── password_reset.html
│       ├── password_reset_confirm.html
│       ├── profile.html
│       └── register.html
├── manage.py                  # Django management script
├── requirements.txt           # Project dependencies
└── .env                       # Environment variables
```

## Installation and Setup

### Prerequisites

- Python 3.11.10
- PostgreSQL Database
- Django
- Virtual Environment (recommended)

### Steps

1. **Clone the repository**

   ```bash
   git clone <repository_url>
   cd bnbu_backend_api
   ```

2. **Create a virtual environment (optional but recommended)**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install the dependencies**

   Make sure you're in the project's root directory (where `requirements.txt` is located):

   ```bash
   pip install -r requirements.txt
   ```

4. **Setup the PostgreSQL Database**

   - Create a PostgreSQL database and user:

     ```sql
     CREATE DATABASE bnbu_db;  -- Replace with your desired database name
     CREATE USER bnbu_user WITH PASSWORD 'your_password';  -- Replace with a secure password
     ALTER ROLE bnbu_user SET client_encoding TO 'utf8';
     ALTER ROLE bnbu_user SET default_transaction_isolation TO 'read committed';
     ALTER ROLE bnbu_user SET timezone TO 'UTC';
     GRANT ALL PRIVILEGES ON DATABASE bnbu_db TO bnbu_user;  -- Grant privileges to the user
     ```

   - Update your `.env` file with the PostgreSQL credentials:

     ```plaintext
     DATABASE_NAME=bnbu_db
     DATABASE_USER=bnbu_user
     DATABASE_PASSWORD=your_password
     DATABASE_HOST=localhost  # Or your PostgreSQL host
     DATABASE_PORT=5432        # Default PostgreSQL port
     ```

5. **Configure the settings.py for PostgreSQL**

   Ensure your `settings.py` file has the correct database settings. It should look something like this:

   ```python
   DATABASES = {
      'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'bnbu_backend_api_db',
        'USER': 'bnbu_admin',
        'PASSWORD': 'admin',
        'HOST': 'localhost',  # Set to 'localhost' or '127.0.0.1'
        'PORT': '',  # Leave empty for default port 5432
      }
   }
   ```

6. **Run migrations**

   Apply database migrations to set up your models:

   ```bash
   python manage.py migrate
   ```

7. **Create a superuser (optional)**

   If you want to access the Django admin interface, create a superuser:

   ```bash
   python manage.py createsuperuser
   ```

8. **Run the server**

   Start the development server:

   ```bash
   python manage.py runserver
   ```

9. **Access the API**

   Open your browser and navigate to `http://127.0.0.1:8000/account/` to access the API.

## Usage

You can interact with the API through the following endpoints:

- **Dashboard**: `/account/`
- **Register**: `/account/register/`
- **Login**: `/account/login/`
- **Profile**: `/account/profile/`
- **Logout**: `/account/logout/`
- **Password Reset**: `/account/password_reset/`
