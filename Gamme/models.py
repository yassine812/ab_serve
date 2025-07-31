from django.db import models
from django.contrib.auth.models import AbstractUser
from decimal import Decimal

# ----------- UTILISATEUR -----------

class User(AbstractUser):
    is_admin = models.BooleanField(default=False, verbose_name='Admin')
    is_op = models.BooleanField(default=False, verbose_name='Opérateur')
    is_rs = models.BooleanField(default=False, verbose_name='Responsable')
    is_ro = models.BooleanField(default=False, verbose_name='RO')

    def __str__(self):
        return self.username


# ----------- MISSION CONTROLE -----------

class MissionControle(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=100, unique=True)
    intitule = models.CharField(max_length=100)
    description = models.TextField()
    produitref = models.CharField(max_length=100)
    statut = models.BooleanField(default=True)
    pdf_file = models.FileField(upload_to='gammes_pdf/', null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mission_created')
    updated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mission_updated', null=True, blank=True)
    
    def __str__(self):
        return self.intitule

    @property
    def latest_gamme(self):
        return self.gammes.order_by('-date_creation').first()


# ----------- GAMME CONTROLE -----------

class GammeControle(models.Model):
    id = models.AutoField(primary_key=True)
    mission = models.ForeignKey(MissionControle, on_delete=models.CASCADE, related_name='gammes')
    intitule = models.CharField(max_length=100)
    No_incident = models.CharField(max_length=100)
    version = models.CharField(max_length=100)
    version_num = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    statut = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamme_created')
    updated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamme_updated', null=True, blank=True)

    def save(self, *args, **kwargs):
        try:
            self.version_num = Decimal(self.version)
        except:
            self.version_num = 1.0
        super().save(*args, **kwargs)

    def __str__(self):
        return self.intitule

def photo_defaut_upload_to(instance, filename):
    """
    Return the path where defect photos should be uploaded.
    Format: photos/defauts/gamme_<gamme_id>/<filename>
    """
    return f'photos/defauts/gamme_{instance.gamme.id}/{filename}'

class PhotoDefaut(models.Model):
    id = models.AutoField(primary_key=True)
    gamme = models.ForeignKey(GammeControle, on_delete=models.CASCADE, related_name='defaut_photos')
    image = models.ImageField(upload_to=photo_defaut_upload_to)
    description = models.CharField(max_length=255, blank=True, default='')
    date_ajout = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='photo_defaut_created', null=True, blank=True)

    class Meta:
        ordering = ['-date_ajout']
        verbose_name = 'Photo de défaut'
        verbose_name_plural = 'Photos de défaut'

    def __str__(self):
        return self.description or f'Photo {self.id} pour {self.gamme.intitule}'
    
    def delete(self, *args, **kwargs):
        """
        Delete the file from storage when the model instance is deleted.
        """
        if self.image:
            storage, path = self.image.storage, self.image.path
            # Delete the model first
            super().delete(*args, **kwargs)
            # Then delete the file
            storage.delete(path)
        else:
            super().delete(*args, **kwargs)


# ----------- OPÉRATION CONTROLE -----------

class OperationControle(models.Model):
    id = models.AutoField(primary_key=True)
    gamme = models.ForeignKey(GammeControle, on_delete=models.CASCADE, null=True, blank=True)
    ordre = models.IntegerField()
    titre = models.CharField(max_length=100)
    description = models.TextField()
    criteres = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='operation_created')
    updated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='operation_updated', null=True, blank=True)

    class Meta:
        unique_together = ('gamme', 'ordre')

    def __str__(self):
        return self.titre


# ----------- PHOTO OPÉRATION -----------

class PhotoOperation(models.Model):
    id = models.AutoField(primary_key=True)
    operation = models.ForeignKey(OperationControle, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='photos/')
    description = models.CharField(max_length=255)
    date_ajout = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='photo_operation_created', null=True, blank=True)

    def __str__(self):
        return self.description

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username}'s Profile"

