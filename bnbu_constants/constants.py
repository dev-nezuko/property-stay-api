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


VALID_FILE_EXTENSION = [".xls", ".xlsx", ".csv"]
REQUIRED_COLS = ["Location", "Price", "Sq. ft.", "Ba", "Br", "Link"]
IMP_COLS = ['Ba', 'Br', 'Price', 'Link']

CURRENCY_USD = "usd"
