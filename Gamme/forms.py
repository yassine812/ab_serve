import os
from django import forms
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from .models import User,Profile
from django.contrib.auth.forms import UserCreationForm
from django.forms.models import inlineformset_factory, modelformset_factory
from .models import GammeControle, MissionControle, OperationControle, PhotoOperation, epi, moyens_controle

# ----------- FORMULAIRE : GammeControle -----------

class GammeControleForm(forms.ModelForm):
    class Meta:
        model = GammeControle
        fields = ['mission', 'intitule', 'statut', 'No_incident', 'commantaire', 'Temps_alloué', 'commantaire_identification', 'commantaire_traitement_non_conforme', 'photo_traitement_non_conforme']
        widgets = {
            'mission': forms.Select(attrs={'class': 'form-select'}),
            'intitule': forms.TextInput(attrs={'class': 'form-control'}),
            'statut': forms.Select(choices=[(True, 'Actif'), (False, 'Inactif')], attrs={'class': 'form-select'}),
            'No_incident': forms.TextInput(attrs={'class': 'form-control'}),
            'commantaire': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'Temps_alloué': forms.NumberInput(attrs={'class': 'form-control'}),
            'commantaire_identification': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'commantaire_traitement_non_conforme': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'photo_traitement_non_conforme': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean_intitule(self):
        intitule = self.cleaned_data.get('intitule')
        if not intitule:
            raise ValidationError("L'intitulé de la gamme ne peut pas être vide.")
        return intitule

    def clean_Temps_alloué(self):
        temps_alloue = self.cleaned_data.get('Temps_alloué')
        if temps_alloue is not None and temps_alloue < 0:
            raise ValidationError("Le temps alloué ne peut pas être négatif.")
        return temps_alloue

# ----------- FORMULAIRE : OperationControle -----------

class OperationControleForm(forms.ModelForm):
    moyenscontrole = forms.ModelMultipleChoiceField(
        queryset=moyens_controle.objects.all().order_by('ordre'),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label='Moyens de contrôle'  
    )
    
    class Meta:
        model = OperationControle
        fields = ['titre', 'description', 'criteres', 'moyen_controle', 'moyenscontrole', 'frequence', 'ordre']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'criteres': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'moyen_controle': forms.TextInput(attrs={'class': 'form-control'}),
            'frequence': forms.NumberInput(attrs={'class': 'form-control'}),
            'ordre': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# ----------- FORMULAIRE : PhotoOperation -----------

class PhotoOperationForm(forms.ModelForm):
    class Meta:
        model = PhotoOperation
        fields = ['image', 'description']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }

# ----------- FORMULAIRE : MissionControle -----------

class MissionControleForm(forms.ModelForm):
    STATUT_CHOICES = [
        (True, 'Actif'),
        (False, 'Inactif'),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convert initial boolean values to string for the form
        if 'statut' in self.initial:
            self.initial['statut'] = str(self.initial['statut'])

    statut = forms.TypedChoiceField(
        choices=STATUT_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    
    def clean_statut(self):
        statut = self.cleaned_data.get('statut')
        # Convert string 'True'/'False' to boolean if needed
        if isinstance(statut, str):
            return statut.lower() == 'true'
        return bool(statut)

    class Meta:
        model = MissionControle
        fields = ['code', 'intitule', 'section', 'client', 'designation', 'description', 'reference', 'statut']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'intitule': forms.TextInput(attrs={'class': 'form-control'}),
            'section': forms.TextInput(attrs={'class': 'form-control'}),
            'client': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

# ----------- FORMULAIRE : Moyen de Contrôle -----------

class MoyenControleForm(forms.ModelForm):
    class Meta:
        model = moyens_controle
        fields = ['nom', 'photo', 'ordre']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'ordre': forms.NumberInput(attrs={'class': 'form-control'}),
        }
    
    def clean_photo(self):
        photo = self.cleaned_data.get('photo', False)
        if photo:
            # Limit file size to 5MB
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("La taille de l'image ne doit pas dépasser 5MB.")
            
            # Check file extension
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            ext = os.path.splitext(photo.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError("Format de fichier non supporté. Utilisez JPG, JPEG, PNG ou GIF.")
        return photo
        
    def clean_ordre(self):
        ordre = self.cleaned_data.get('ordre')
        if ordre is not None:
            # Check if this is an update or create operation
            instance = getattr(self, 'instance', None)
            
            # Query for existing moyens_controle with the same ordre
            queryset = moyens_controle.objects.filter(ordre=ordre)
            
            # If this is an update, exclude the current instance from the query
            if instance and instance.pk:
                queryset = queryset.exclude(pk=instance.pk)
                
            if queryset.exists():
                raise forms.ValidationError("Cette valeur d'ordre est déjà utilisée. Veuillez en choisir une autre.")
                
        return ordre

# ----------- FORMULAIRE : Inscription Utilisateur -----------
class RegisterForm(UserCreationForm):
    username = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_op = True  # Set role to admin by default
        user.is_rs = False
        if commit:
            user.save()
        return user
# ----------- FORMULAIRE : Mise à jour du profil -----------
class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['username'].label = 'Nom d\'utilisateur'
            self.fields['email'].label = 'Email'
            self.fields['first_name'].label = 'Prénom'
            self.fields['last_name'].label = 'Nom'

    def save(self, commit=True):
        return super().save(commit)

# ----------- FORMULAIRE : EPI -----------

class EpiForm(forms.ModelForm):
    class Meta:
        model = epi
        fields = ['nom', 'photo', 'commentaire']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom de l\'équipement',
                'required': 'required',
            }),
            'commentaire': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description ou notes sur l\'équipement',
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'required': 'required',
            }),
        }
        labels = {
            'nom': 'Nom de l\'équipement',
            'photo': 'Photo de l\'équipement',
            'commentaire': 'Commentaires',
        }
        help_texts = {
            'photo': 'Formats supportés: JPG, PNG. Taille maximale: 5 Mo.',
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:  # Only validate if a file was uploaded
            if hasattr(photo, 'size') and photo.size > 5*1024*1024:  # 5MB limit
                raise forms.ValidationError("La taille de l'image ne doit pas dépasser 5 Mo.")
            if hasattr(photo, 'content_type') and not photo.content_type.startswith('image/'):
                raise forms.ValidationError("Veuillez télécharger un fichier image valide.")
        return photo

# ----------- INLINE FORMSETS -----------

# GammeControle inline formset for MissionControle
UpdateGammeFormSet = inlineformset_factory(
    MissionControle,
    GammeControle,
    form=GammeControleForm,
    extra=0,
    can_delete=True
)

# OperationControle inline formset for GammeControle
UpdateOperationFormSet = inlineformset_factory(
    GammeControle,
    OperationControle,
    form=OperationControleForm,
    extra=1,
    can_delete=True,
    fields=['titre', 'description', 'criteres', 'moyen_controle', 'frequence', 'ordre', 'moyenscontrole']
)

# PhotoOperation inline formset for OperationControle
UpdatePhotoFormSet = inlineformset_factory(
    OperationControle,
    PhotoOperation,
    form=PhotoOperationForm,
    extra=1,
    max_num=5,  # Allow up to 5 photos
    can_delete=True
)

# ----------- MODelformset for Dashboard or separated forms (optional) -----------

OperationControleFormSet = modelformset_factory(
    OperationControle,
    form=OperationControleForm,
    extra=1,
    can_delete=False
)

PhotoOperationFormSet = modelformset_factory(
    PhotoOperation,
    form=PhotoOperationForm,
    extra=1,
    max_num=5,  # Allow up to 5 photos
    can_delete=True
)
gammeFormSet = inlineformset_factory(
    MissionControle,
    GammeControle,
    fields=['intitule', 'statut'],
    extra=0,
    can_delete=True
)