from django.db import models

# Search is a stateless, query-only app that operates against the FAISS vector
# index and Document objects owned by the documents app.
# No dedicated database models are needed here.
