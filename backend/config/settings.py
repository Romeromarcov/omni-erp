import os

env = os.environ.get("DJANGO_ENV", "dev")
if env == "prod":
    from .settings_prod import *
else:
    from .settings_dev import *
