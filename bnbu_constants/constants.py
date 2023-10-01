PENDING = "Pending"
APPROVED = "Approved"
REJECTED = "Rejected"
ERROR = "Error"

RENTAL_PROPERY_STATUS_CHOICES = [
    (PENDING, "Pending"),
    (APPROVED, "Approved"),
    (REJECTED, "Rejected"),
    (ERROR, "Error"),
]


# Legacy .xls would need xlrd, which is not installed; openpyxl reads .xlsx.
VALID_FILE_EXTENSION = [".xlsx", ".csv"]
REQUIRED_COLS = ["Location", "Price", "Sq. ft.", "Ba", "Br", "Link"]
IMP_COLS = ['Ba', 'Br', 'Price', 'Link']

CURRENCY_USD = "usd"
