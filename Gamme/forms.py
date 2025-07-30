from django import forms
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from .models import User,Profile
from django.contrib.auth.forms import UserCreationForm
from django.forms.models import inlineformset_factory, modelformset_factory
from .models import GammeControle, MissionControle, OperationControle, PhotoOperation

# ----------- FORMULAIRE : GammeControle -----------

class GammeControleForm(forms.ModelForm):
    class Meta:
        model = GammeControle
        fields = ['mission', 'intitule', 'statut']
        widgets = {
            'mission': forms.Select(attrs={'class': 'form-select'}),
            'intitule': forms.TextInput(attrs={'class': 'form-control'}),
            'statut': forms.Select(choices=[(True, 'Actif'), (False, 'Inactif')], attrs={'class': 'form-select'}),
        }

# ----------- FORMULAIRE : OperationControle -----------

class OperationControleForm(forms.ModelForm):
    class Meta:
        model = OperationControle
        fields = ['titre', 'description', 'criteres', 'ordre']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'criteres': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
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

    statut = forms.TypedChoiceField(
        choices=STATUT_CHOICES,
        coerce=lambda x: x == 'True',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = MissionControle
        fields = ['code', 'intitule', 'description', 'produitref', 'statut']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'intitule': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'produitref': forms.TextInput(attrs={'class': 'form-control'}),
        }

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
    can_delete=True
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