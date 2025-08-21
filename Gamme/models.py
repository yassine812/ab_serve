from ast import Num
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
    reference = models.CharField(max_length=100)
    statut = models.BooleanField(default=True)
    section = models.CharField(max_length=100, null=True, blank=True)
    client = models.CharField(max_length=100, null=True, blank=True)
    designation = models.CharField(max_length=100, null=True, blank=True)
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
    Num_gamme = models.CharField(max_length=100, null=True, blank=True)
    commantaire = models.TextField(null=True, blank=True)
    Temps_alloué = models.IntegerField(null=True, blank=True)
    commantaire_identification = models.CharField(max_length=100, null=True, blank=True)
    commantaire_traitement_non_conforme = models.CharField(max_length=100, null=True, blank=True)
    # Use a callable to build a deterministic path instead of a format string with {instance...}
    def photo_traitement_non_conforme_upload_to(instance, filename):
        # Store under photos/non_conformes/gamme_<gamme_id>/<filename>
        # instance is GammeControle
        gid = instance.id or 0
        return f'photos/non_conformes/gamme_{gid}/{filename}'

    photo_traitement_non_conforme = models.ImageField(upload_to=photo_traitement_non_conforme_upload_to, null=True, blank=True)
    No_incident = models.CharField(max_length=100)
    version = models.CharField(max_length=100)
    version_num = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    statut = models.BooleanField(default=True)
    est_active = models.BooleanField(default=True, verbose_name='Est active')
    
    picto_s = models.BooleanField(default=False, verbose_name='Picto S')
    picto_r = models.BooleanField(default=False, verbose_name='Picto R')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamme_created')
    updated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamme_updated', null=True, blank=True)
    epis = models.ManyToManyField('epi', related_name='gammes', blank=True, verbose_name='Équipements de Protection Individuelle')
    moyens_controle = models.ManyToManyField('moyens_controle', related_name='gammes', blank=True, verbose_name='Moyens de Contrôle')

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
class Photolimiteacceptable(models.Model):
    id = models.AutoField(primary_key=True)
    gamme = models.ForeignKey(GammeControle, on_delete=models.CASCADE, related_name='limiteacceptable_photos')
    image = models.ImageField(upload_to=photo_defaut_upload_to)
    description = models.CharField(max_length=255, blank=True, default='')
    date_ajout = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='limiteacceptable_created', null=True, blank=True)

    class Meta:
        ordering = ['-date_ajout']
        verbose_name = 'Photo de limite acceptable'
        verbose_name_plural = 'Photos de limite acceptable'

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
    gamme = models.ForeignKey('GammeControle', on_delete=models.CASCADE, related_name='operations', null=True, blank=True)
    ordre = models.IntegerField(default=1)
    titre = models.CharField(max_length=100, default='Nouvelle opération')
    description = models.TextField(blank=True, default='')
    moyenscontrole = models.ManyToManyField('moyens_controle', related_name='operations', blank=True)
    moyen_controle = models.CharField(max_length=255, blank=True, default='', verbose_name='Moyen de contrôle')
    frequence = models.IntegerField(default=1)
    criteres = models.TextField(blank=True, default='')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='operation_created')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='operation_updated', null=True, blank=True)

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

# ----------- VALIDATION -----------

class validation(models.Model):
    id_validation = models.AutoField(primary_key=True)
    operation = models.ForeignKey('OperationControle', on_delete=models.CASCADE, related_name='validations', null=True, blank=True)
    gamme = models.ForeignKey('GammeControle', on_delete=models.CASCADE, related_name='validations', null=True, blank=True)
    user_ro = models.ForeignKey(User, on_delete=models.CASCADE, related_name='validations_ro')
    date_validation_user_ro = models.DateTimeField(auto_now_add=True)
    user_clt = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='validations_clt', null=True, blank=True)
    date_validation_user_clt = models.DateTimeField(null=True, blank=True)
    commentaire = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(operation__isnull=False) | models.Q(gamme__isnull=False)
                ) & ~models.Q(operation__isnull=False, gamme__isnull=False),
                name='only_one_validation_target',
                violation_error_message='Une validation doit être liée soit à une opération, soit à une gamme, mais pas aux deux.'
            )
        ]
        verbose_name = 'Validation'
        verbose_name_plural = 'Validations'

    def clean(self):
        if not self.operation and not self.gamme:
            raise ValidationError('Une validation doit être liée à une opération ou à une gamme.')
        if self.operation and self.gamme:
            raise ValidationError('Une validation ne peut pas être liée à la fois à une opération et à une gamme.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.gamme:
            return f"Validation gamme {self.gamme.intitule} - {self.user_ro} - {self.date_validation_user_ro.strftime('%d/%m/%Y %H:%M')}"
        return f"Validation opération {self.operation} - {self.user_ro} - {self.date_validation_user_ro.strftime('%d/%m/%Y %H:%M')}"

# ----------- EPI (Équipement de Protection Individuelle) -----------

class epi(models.Model):
    id = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='photos/epi/')
    commentaire = models.TextField(blank=True)

    def __str__(self):
        return self.nom

# ----------- MOYENS CONTROLE -----------

class moyens_controle(models.Model):
    id = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='photos/moyens_controle/')
    ordre = models.IntegerField()
   

    def __str__(self):
        return f"{self.nom} (Ordre: {self.ordre})"
    