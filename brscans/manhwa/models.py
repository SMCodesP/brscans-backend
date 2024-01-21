from django.db import models


# Create your models here.
class Manhwa(models.Model):
    title = models.CharField(max_length=100)
    author = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.title
