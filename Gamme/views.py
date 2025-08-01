from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Max
import os
import logging
from django.views.generic import ListView,DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.forms import inlineformset_factory
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import MissionControle, GammeControle, OperationControle, PhotoOperation, PhotoDefaut, User
from .forms import MissionControleForm, GammeControleForm,ProfileUpdateForm, OperationControleForm,OperationControleFormSet, PhotoOperationForm, UpdateGammeFormSet, UpdateOperationFormSet, UpdatePhotoFormSet,RegisterForm
from django.contrib.auth import logout
from django.views import View
from django.contrib.auth.views import LoginView
gammeFormSet = inlineformset_factory(   
    MissionControle,
    GammeControle,
    fields=['intitule', 'version', 'statut'],
    extra=0,
    can_delete=True
)
class MissionControleUpdateView(LoginRequiredMixin,View):
    template_name = 'gamme/missioncontrole_update.html'

    def get(self, request, pk):
        missioncontrole = get_object_or_404(MissionControle, pk=pk)
        operation_formset = OperationControleFormSet(prefix='form', queryset=OperationControle.objects.none())
        
        # Get gammes with prefetched photos, ordered by last update date
        gammes = GammeControle.objects.filter(mission=missioncontrole)
        gammes = gammes.prefetch_related('defaut_photos').order_by('-date_mise_a_jour')
        
        # Debug: Log gamme IDs and their photo counts
        if logger.isEnabledFor(logging.DEBUG):
            for gamme in gammes:
                logger.debug(f"Gamme {gamme.id} has {gamme.defaut_photos.count()} defect photos")
            
        return render(request, self.template_name, {
            'missioncontrole': missioncontrole,
            'gammes': gammes,
            'operation_formset': operation_formset,
        })

    def post(self, request, pk):
        missioncontrole = get_object_or_404(MissionControle, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            # --- Mise à jour des champs mission ---
            missioncontrole.code = request.POST.get('code', missioncontrole.code)
            missioncontrole.intitule = request.POST.get('intitule', missioncontrole.intitule)
            missioncontrole.produitref = request.POST.get('produitref', missioncontrole.produitref)
            missioncontrole.statut = request.POST.get('statut', str(missioncontrole.statut)) == 'True'
            missioncontrole.save()

            # --- Mise à jour des gammes et opérations ---
            gammes = GammeControle.objects.filter(mission=missioncontrole)
            changes_made = False
            
            for gamme in gammes:
                intitule = request.POST.get(f'{gamme.id}-intitule', gamme.intitule)
                # Ensure gamme title follows the format 'Gamme: [Mission Title]' if it's empty or being reset
                if not intitule or intitule.strip() == '':
                    intitule = f"Gamme: {missioncontrole.intitule}"
                statut = request.POST.get(f'{gamme.id}-statut', 'False')
                # Initialize changement_detecte at the beginning of the gamme loop
                changement_detecte = False

                if intitule != gamme.intitule or (statut == 'True') != gamme.statut:
                    changement_detecte = True

                # Process existing operations
                for op in gamme.operationcontrole_set.all():
                    titre = request.POST.get(f"{op.id}-titre", op.titre)
                    ordre = request.POST.get(f"{op.id}-ordre", op.ordre)
                    description = request.POST.get(f"{op.id}-description", op.description)
                    criteres = request.POST.get(f"{op.id}-criteres", op.criteres)

                    if titre != op.titre or str(ordre) != str(op.ordre) or description != op.description or criteres != op.criteres:
                        changement_detecte = True

                    # Process existing photos
                    for photo in op.photooperation_set.all():
                        desc = request.POST.get(f"photo_{photo.id}_description", photo.description)
                        delete = request.POST.get(f"photo_{photo.id}_DELETE", None)
                        if desc != photo.description or delete is not None:
                            changement_detecte = True

                    # Check for new dynamic photos
                    for key in request.FILES.keys():
                        if key.startswith(f'photo_{op.id}_'):
                            changement_detecte = True
                            break

                # Check for new operations
                for key in request.POST.keys():
                    if key.startswith(f"newop_{gamme.id}_"):
                        changement_detecte = True
                        break

                # Check for files related to new operations
                for key in request.FILES.keys():
                    if key.startswith("newphoto_") or key.startswith(f"newop_{gamme.id}_") or key.startswith("formop_"):
                        changement_detecte = True
                        break

                # Initialize new_gamme to the current gamme by default
                new_gamme = gamme
                
                # Si changement → créer nouvelle version de la gamme
                if changement_detecte:
                    changes_made = True
                    previous_versions = GammeControle.objects.filter(mission=missioncontrole, intitule=gamme.intitule).order_by('-version')
                    latest_version = float(previous_versions.first().version) if previous_versions.exists() else 1.0
                    previous_versions.update(statut=False)
                    next_version = round(latest_version + 0.1, 1)

                    no_incident = request.POST.get(f'{gamme.id}-No_incident', gamme.No_incident)
                    new_gamme = GammeControle.objects.create(
                        mission=missioncontrole,
                        intitule=intitule,
                        No_incident=no_incident,
                        statut=(statut == 'True'),
                        version=next_version,
                        created_by=request.user
                    )

                # Get the maximum order value from existing operations in the new gamme
                max_order = OperationControle.objects.filter(gamme=new_gamme).aggregate(Max('ordre'))['ordre__max'] or 0
                
                # First, collect all operations with their new order values
                operations_to_update = []
                for op in gamme.operationcontrole_set.all():
                    # Get the new order value from the form
                    new_order = request.POST.get(f"{op.id}-ordre")
                    try:
                        new_order = int(new_order) if new_order is not None else op.ordre
                    except (ValueError, TypeError):
                        new_order = op.ordre
                    
                    operations_to_update.append({
                        'op': op,
                        'new_order': new_order,
                        'titre': request.POST.get(f"{op.id}-titre", op.titre),
                        'description': request.POST.get(f"{op.id}-description", op.description),
                        'criteres': request.POST.get(f"{op.id}-criteres", op.criteres)
                    })
                
                # Sort operations by their new order to ensure consistent ordering
                operations_to_update.sort(key=lambda x: x['new_order'])
                
                # Now create the operations in the new gamme with their new order values
                current_order = 1
                for op_data in operations_to_update:
                    # Ensure the order is unique and sequential
                    while OperationControle.objects.filter(gamme=new_gamme, ordre=current_order).exists():
                        current_order += 1
                    
                    # Create the new operation with the updated values
                    new_op = OperationControle.objects.create(
                        gamme=new_gamme,
                        titre=op_data['titre'],
                        ordre=current_order,  # Use the sequential order
                        description=op_data['description'],
                        criteres=op_data['criteres'],
                        created_by=request.user
                    )
                    current_order += 1
                    
                    # Get the original operation for copying photos
                    op = op_data['op']

                    # Photos existantes copiées sauf celles à supprimer
                    for photo in op.photooperation_set.all():
                        if request.POST.get(f"photo_{photo.id}_DELETE"):
                            continue
                            
                        # Récupérer la description mise à jour ou utiliser l'ancienne
                        photo_description = request.POST.get(f"photo_{photo.id}_description", photo.description)
                        
                        PhotoOperation.objects.create(
                            operation=new_op,
                            image=photo.image,
                            description=photo_description
                        )

                    # Nouvelles photos dynamiques - Vérifier les deux formats
                    # 1. Ancien format: photo_{op.id}_{i}_image
                    i = 0
                    while True:
                        # Vérifier l'ancien format
                        old_image_key = f'photo_{op.id}_{i}_image'
                        old_desc_key = f'photo_{op.id}_{i}_description'
                        
                        # Vérifier le nouveau format: form-{op.id}-photo-{i}-image
                        new_image_key = f'form-{op.id}-photo-{i}-image'
                        new_desc_key = f'form-{op.id}-photo-{i}-description'
                        
                        image_key = None
                        desc_key = None
                        
                        # Vérifier quel format est présent dans la requête
                        if old_image_key in request.FILES:
                            image_key = old_image_key
                            desc_key = old_desc_key
                        elif new_image_key in request.FILES:
                            image_key = new_image_key
                            desc_key = new_desc_key
                        
                        if image_key and image_key in request.FILES:
                            image = request.FILES[image_key]
                            description = request.POST.get(desc_key, '')
                            
                            # Journaliser pour le débogage
                            print(f"Sauvegarde d'une nouvelle photo pour l'opération {new_op.id}")
                            print(f"  - Nom du fichier: {image.name}")
                            print(f"  - Taille: {image.size} octets")
                            print(f"  - Description: {description}")
                            
                            PhotoOperation.objects.create(
                                operation=new_op,
                                image=image,
                                description=description
                            )
                            i += 1
                        else:
                            # Aucune photo supplémentaire dans aucun format
                            break

                # Nouvelles opérations manuelles
                i = 0
                while True:
                    # First check for the operation fields with the current index
                    titre = request.POST.get(f'newop_{gamme.id}_{i}_titre')
                    
                    # Debug: Log all FILES keys
                    print(f"\nDebug - FILES keys: {list(request.FILES.keys())}")
                    print(f"Looking for files with prefix: newop_{gamme.id}_{i}_photo_")
                    
                    if not titre:
                        # If no title, check if there are any files for this operation
                        has_files = any(k.startswith(f'newop_{gamme.id}_{i}_photo_') for k in request.FILES.keys())
                        print(f"Operation {i} - has_files: {has_files}")
                        if not has_files:
                            print(f"No files found for operation {i}, breaking")
                            break
                        # If there are files but no title, use a default title
                        titre = f"Nouvelle opération {i+1}"
                    
                    # Get other operation fields
                    description = request.POST.get(f'newop_{gamme.id}_{i}_description', '')
                    criteres = request.POST.get(f'newop_{gamme.id}_{i}_criteres', '')
                    
                    # Get the next available order value for this gamme
                    max_ordre = OperationControle.objects.filter(
                        gamme=new_gamme
                    ).aggregate(Max('ordre'))['ordre__max'] or 0
                    next_ordre = max_ordre + 1
                    
                    print(f"Creating new operation with ordre: {next_ordre} for gamme {new_gamme.id}")
                    
                    # Create the new operation
                    new_op = OperationControle.objects.create(
                        gamme=new_gamme,
                        titre=titre,
                        ordre=next_ordre,  # Use the calculated next order
                        description=description,
                        criteres=criteres,
                        created_by=request.user
                    )

                    # Process photos for this operation
                    print(f"\nProcessing photos for operation {i} (gamme: {gamme.id}, new_op: {new_op.id})")
                    print(f"All FILES keys: {list(request.FILES.keys())}")
                    
                    # Track processed photo indices to handle multiple file inputs
                    processed_photos = set()
                    
                    # First, handle any file uploads with the expected naming pattern
                    for file_key in request.FILES.keys():
                        expected_prefix = f'newop_{gamme.id}_{i}_photo_'
                        if file_key.startswith(expected_prefix) and file_key.endswith('_image'):
                            print(f"Found matching file input: {file_key}")
                            
                            try:
                                # Extract the photo index from the key (e.g., 'newop_1_0_photo_0_image' -> 0)
                                parts = file_key.split('_')
                                if len(parts) >= 6:  # Format: newop_<gamme>_<op>_photo_<index>_image
                                    photo_idx = int(parts[-2])
                                    
                                    if photo_idx in processed_photos:
                                        print(f"  - Photo index {photo_idx} already processed, skipping")
                                        continue
                                    
                                    # Get the corresponding description
                                    desc_key = f'newop_{gamme.id}_{i}_photo_{photo_idx}_description'
                                    description = request.POST.get(desc_key, 'No description')
                                    
                                    print(f"  - Processing photo index {photo_idx}")
                                    print(f"  - Description key: {desc_key}")
                                    print(f"  - Description value: {description}")
                                    
                                    # Create the photo record
                                    try:
                                        print(f"  - Creating PhotoOperation for {file_key}")
                                        photo = PhotoOperation.objects.create(
                                            operation=new_op,
                                            image=request.FILES[file_key],
                                            description=description
                                        )
                                        print(f"  - Successfully created photo {photo.id} for operation {new_op.id}")
                                        print(f"  - File path: {photo.image}")
                                        print(f"  - Description: {description}")
                                        processed_photos.add(photo_idx)
                                    except Exception as e:
                                        print(f"  - Error creating photo: {str(e)}")
                                        import traceback
                                        traceback.print_exc()
                                else:
                                    print(f"  - Unexpected file key format: {file_key}")
                                    
                            except (ValueError, IndexError) as e:
                                print(f"  - Error parsing photo index from {file_key}: {str(e)}")
                                import traceback
                                traceback.print_exc()
                                continue
                    
                    # Old photo processing code removed - using new method only
                    
                    i += 1

        except Exception as e:
            # Log the error for debugging
            import traceback
            error_message = f"Error in MissionControleUpdateView: {str(e)}\n{traceback.format_exc()}"
            print(error_message)
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': f'Une erreur est survenue lors de la mise à jour: {str(e)}'
                }, status=500)
                
            # For non-AJAX requests, re-raise the exception
            raise
            
        # --- Création d'une nouvelle gamme complète ---
        gamme_intitule = request.POST.get('gamme_intitule')
        gamme_no_incident = request.POST.get('gamme_No_incident', '')
        gamme_statut = request.POST.get('gamme_statut')
        
        if gamme_intitule and gamme_statut is not None:
            # Create the new gamme
            new_gamme = GammeControle.objects.create(
                mission=missioncontrole,
                intitule=gamme_intitule,
                No_incident=gamme_no_incident,
                statut=gamme_statut == 'True',
                created_by=request.user,
                version=1.0
            )
            
            # Debug: Print all form data with more details
            print("\n=== RAW REQUEST DATA ===")
            print(f"Method: {request.method}")
            print(f"Content-Type: {request.content_type}")
            print(f"POST data keys: {list(request.POST.keys())}")
            print(f"FILES data keys: {list(request.FILES.keys())}")
            
            print("\n=== FORM DATA ===")
            for key, value in request.POST.items():
                print(f"{key}: {value}")
            
            print("\n=== FILES ===")
            for key, file_obj in request.FILES.items():
                print(f"{key}: {file_obj.name} (size: {file_obj.size} bytes, type: {file_obj.content_type})")
            
            # Print all request headers for debugging
            print("\n=== REQUEST HEADERS ===")
            for header, value in request.META.items():
                if header.startswith('HTTP_') or header in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                    print(f"{header}: {value}")
            
            # Process operation forms using Django formset
            operation_formset = OperationControleFormSet(
                request.POST, 
                request.FILES,
                prefix='form',
                queryset=OperationControle.objects.none()
            )
            
            print("\n=== DEBUG: Processing operation formset ===")
            print(f"Formset is valid: {operation_formset.is_valid()}")
            
            if operation_formset.is_valid():
                operations = operation_formset.save(commit=False)
                print(f"Found {len(operations)} operations to save")
                
                for i, operation in enumerate(operations):
                    operation.gamme = new_gamme
                    operation.created_by = request.user
                    operation.save()
                    print(f"Saved operation {i}: {operation.titre} (ID: {operation.id})")
                    
                    # Process photo uploads for this operation
                    photo_files = {}
                    photo_descriptions = {}
                    
                    # Find all photo files and descriptions for this operation
                    for key, file_obj in request.FILES.items():
                        if key.startswith(f'form-{i}-photo-') and key.endswith('-image'):
                            photo_index = key.split('-')[3]
                            photo_files[photo_index] = file_obj
                    
                    for key, value in request.POST.items():
                        if key.startswith(f'form-{i}-photo-') and key.endswith('-description'):
                            photo_index = key.split('-')[3]
                            photo_descriptions[photo_index] = value
                    
                    # Save photos for this operation
                    for photo_index, file_obj in photo_files.items():
                        description = photo_descriptions.get(photo_index, '')
                        photo = PhotoOperation(
                            operation=operation,
                            image=file_obj,
                            description=description,
                            created_by=request.user
                        )
                        photo.save()
                        print(f"  - Saved photo: {file_obj.name} (ID: {photo.id})")
                        
            else:
                print("Formset errors:", operation_formset.errors)
                print("Non-form errors:", operation_formset.non_form_errors())

        return redirect('Gamme:missioncontrole_list')


class DashboardView(LoginRequiredMixin, View):
    template_name = 'gamme/dashboard.html'

    def get_context_data(self, **kwargs):
        context = {
            'missions': MissionControle.objects.all(),
            'gammes': GammeControle.objects.all(),
            'form': GammeControleForm(),
            'operation_formset': UpdateOperationFormSet(queryset=OperationControle.objects.none(), prefix='operation_formset')
        }
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())

    def post(self, request, *args, **kwargs):
        form_type = request.POST.get("form_type")
        is_mission_creation = form_type == "mission"
        # Initialize forms
        mission_form = None
        gamme_form = None
        operation_formset = UpdateOperationFormSet(request.POST or None, request.FILES or None, 
                                                prefix='operation_formset', 
                                                queryset=OperationControle.objects.none())
        if form_type == "mission":
            mission_form = MissionControleForm(request.POST, request.FILES)
            
            if mission_form.is_valid():
                try:
                    with transaction.atomic():
                        # Save mission first
                        mission = mission_form.save(commit=False)
                        mission.created_by = request.user
                        mission.save()
                        
                        # Get gamme data from the form
                        gamme_intitule = request.POST.get("gamme_intitule")
                        if gamme_intitule:
                            # Create gamme linked to the mission
                            gamme = GammeControle.objects.create(
                                mission=mission,
                                intitule=gamme_intitule,
                                No_incident=request.POST.get("gamme_No_incident", ""),
                                statut=request.POST.get("gamme_statut", "True") == "True",
                                version="1.0",
                                created_by=request.user
                            )
                            
                            # Save operations if any
                            if operation_formset.is_valid():
                                self.save_operations(request, operation_formset, gamme)
                            
                            messages.success(request, "Mission, gamme et opérations enregistrées avec succès.")
                            
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return JsonResponse({
                                    'success': True,
                                    'gamme_created': True,
                                    'redirect_url': reverse('Gamme:missioncontrole_list')
                                })
                            return redirect("Gamme:missioncontrole_list")
                        else:
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return JsonResponse({
                                    'success': False,
                                    'error': 'Erreur dans le formulaire d\'opérations',
                                    'errors': dict(operation_formset.errors)
                                }, status=400)
                            messages.warning(request, "Mission enregistrée, mais certaines opérations n'ont pas pu être enregistrées.")
                            self.log_operation_formset_errors(operation_formset)
                except Exception as e:
                    error_msg = f"Erreur lors de la création de la gamme: {str(e)}"
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': error_msg
                        }, status=400)
                    messages.error(request, error_msg)
                else:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'gamme_created': gamme_created,
                            'message': 'Mission enregistrée avec succès.'
                        })
                    messages.success(request, "Mission enregistrée avec succès.")
                    return redirect("Gamme:missioncontrole_list")

            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': 'Erreur de validation du formulaire',
                        'errors': dict(mission_form.errors)
                    }, status=400)
                for field, errors in mission_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

        elif form_type == "gamme":
            gamme_form = GammeControleForm(request.POST, request.FILES)
            operation_formset = UpdateOperationFormSet(
                request.POST, 
                request.FILES, 
                prefix='operation_formset',
                queryset=OperationControle.objects.none()
            )
            
            if gamme_form.is_valid():
                try:
                    gamme = gamme_form.save(commit=False)
                    gamme.No_incident = request.POST.get("No_incident")
                    gamme.created_by = request.user
                    gamme.version = "1.0"
                    gamme.save()

                    if operation_formset.is_valid():
                        self.save_operations(request, operation_formset, gamme)
                        messages.success(request, "Gamme et opérations enregistrées avec succès.")
                        return redirect("Gamme:gammecontrole_list")
                    else:
                        messages.warning(request, "Gamme enregistrée, mais certaines opérations n'ont pas pu être enregistrées.")
                        self.log_operation_formset_errors(operation_formset)
                        
                except Exception as e:
                    messages.error(request, f"Erreur lors de l'enregistrement de la gamme: {str(e)}")
            else:
                for field, errors in gamme_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

        else:
            messages.error(request, f"Type de formulaire non reconnu: {form_type}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': f'Type de formulaire non reconnu: {form_type}'
                }, status=400)
            return redirect('Gamme:dashboard')

        # Handle AJAX requests for form errors
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Veuillez corriger les erreurs du formulaire.',
                'form_errors': dict(mission_form.errors if form_type == 'mission' else gamme_form.errors)
            }, status=400)
            
        # Prepare context for re-rendering the form with errors
        context = self.get_context_data()
        if form_type == 'gamme':
            context['form'] = gamme_form or GammeControleForm()
        else:
            context['form'] = GammeControleForm()
            
        context['operation_formset'] = operation_formset
        context['form_data'] = request.POST
        context['active_tab'] = form_type
        
        return render(request, self.template_name, context)

    def save_operations(self, request, formset, gamme):
        for i, form in enumerate(formset.forms):
            if form.is_valid() and form.cleaned_data.get('titre'):
                # Create the operation from the formset's data
                operation = OperationControle.objects.create(
                    gamme=gamme,
                    ordre=form.cleaned_data.get('ordre', i + 1),
                    titre=form.cleaned_data['titre'],
                    description=form.cleaned_data['description'],
                    criteres=form.cleaned_data['criteres'],
                    created_by=request.user
                )

                # Process file uploads for this operation
                for key, file_obj in request.FILES.items():
                    if key.startswith(f'operation_formset-{i}-photo_image'):
                        # Get the corresponding description
                        desc_key = key.replace('_image', '_description')
                        description = request.POST.get(desc_key, '')
                        
                        if file_obj:  # Only save if we have an actual file
                            try:
                                PhotoOperation.objects.create(
                                    operation=operation,
                                    image=file_obj,
                                    description=description,
                                    created_by=request.user
                                )
                            except Exception as e:
                                # Log the error but don't fail the entire operation
                                print(f"Error saving photo: {str(e)}")
                                messages.error(request, f"Erreur lors de l'enregistrement d'une photo: {str(e)}")

    def log_operation_formset_errors(self, formset):
        for i, form in enumerate(formset.forms):
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(self.request, f"Opération {i + 1} - {field}: {error}")

class GammeControleCreateView(LoginRequiredMixin,View):
    template_name = 'gamme/gammecontrole_create.html'

    def get(self, request):
        form = GammeControleForm()
        missions = MissionControle.objects.all()
        return render(request, self.template_name, {
            'form': form,
            'missions': missions
        })

    def post(self, request):
        form = GammeControleForm(request.POST, request.FILES)
        missions = MissionControle.objects.all()

        if not form.is_valid():
            messages.error(request, "Formulaire de la gamme invalide.")
            return render(request, self.template_name, {
                'form': form,
                'missions': missions
            })

        gamme = form.save(commit=False)
        gamme.created_by = request.user

        # Version initiale à 1.0 si non définie
        if not gamme.version:
            gamme.version = '1.0'

        mission_id = request.POST.get('mission')
        if mission_id:
            try:
                mission = MissionControle.objects.get(id=mission_id)
                gamme.mission = mission
                # Set gamme title to 'Gamme: [Mission Title]' if not already set
                if not gamme.intitule or gamme.intitule == '':
                    gamme.intitule = f"Gamme: {mission.intitule}"
            except MissionControle.DoesNotExist:
                messages.error(request, "Mission invalide sélectionnée.")
                return render(request, self.template_name, {
                    'form': form,
                    'missions': missions
                })
        else:
            messages.error(request, "Veuillez sélectionner une mission.")
            return render(request, self.template_name, {
                'form': form,
                'missions': missions
            })

        gamme.save()

        # Création des opérations liées, avec created_by
        op_index = 0
        while True:
            titre = request.POST.get(f'operation_{op_index}_titre')
            if not titre:
                break  # fin des opérations

            ordre = request.POST.get(f'operation_{op_index}_ordre') or 0
            description = request.POST.get(f'operation_{op_index}_description', '')
            criteres = request.POST.get(f'operation_{op_index}_criteres', '')

            operation = OperationControle.objects.create(
                gamme=gamme,
                titre=titre,
                ordre=int(ordre),
                description=description,
                criteres=criteres,
                created_by=request.user,   # IMPORTANT : assigner l'utilisateur ici
            )

            # Création des photos liées
            photo_index = 0
            while True:
                photo_key = f'photo_{op_index}_{photo_index}_image'
                desc_key = f'photo_{op_index}_{photo_index}_description'

                image = request.FILES.get(photo_key)
                description_photo = request.POST.get(desc_key, '')

                if not image:
                    break  # plus de photo

                PhotoOperation.objects.create(
                    operation=operation,
                    image=image,
                    description=description_photo
                )
                photo_index += 1

            op_index += 1

        messages.success(request, "La gamme, ses opérations et photos ont été enregistrées avec succès.")
        return redirect('Gamme:gammecontrole_list')

class GammeControleListView(LoginRequiredMixin, ListView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user 
        return context


class GammeControleUpdateView(LoginRequiredMixin,UpdateView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_update.html'
    fields = ['mission', 'intitule', 'statut']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        OperationFormSet = inlineformset_factory(
            GammeControle,
            OperationControle,
            fields=('titre', 'ordre', 'description', 'criteres'),
            extra=0,
            can_delete=True,
        )

        if self.request.method == 'POST':
            operation_formset = OperationFormSet(self.request.POST, self.request.FILES, instance=self.object)
        else:
            operation_formset = OperationFormSet(instance=self.object)

        # Construire une liste (form, photos) pour chaque opération existante
        operation_forms_with_photos = []
        for form in operation_formset.forms:
            operation_instance = form.instance
            photos = PhotoOperation.objects.filter(operation=operation_instance) if operation_instance.pk else []
            operation_forms_with_photos.append({
                'form': form,
                'photos': photos,
            })

        context['operation_forms_with_photos'] = operation_forms_with_photos
        context['operation_formset'] = operation_formset
        context['missions'] = MissionControle.objects.all()

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        operation_formset = context['operation_formset']
        if operation_formset.is_valid():
            self.object = form.save()
            operation_formset.instance = self.object
            operation_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

class GammeControleDetailView(LoginRequiredMixin, DetailView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_detail.html'
    context_object_name = 'gamme'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['operations'] = OperationControle.objects.filter(gamme=self.object).order_by('ordre')
        return context

class GammeControleDeleteView(LoginRequiredMixin,DeleteView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_delete.html'
    success_url = reverse_lazy('Gamme:gammecontrole_list')


class MissionControleCreateView(LoginRequiredMixin,View):
    template_name = 'gamme/missioncontrole_create.html'

    def get(self, request):
        mission_form = MissionControleForm()
        return render(request, self.template_name, {
            'mission_form': mission_form,
        })

    def post(self, request):
        mission_form = MissionControleForm(request.POST)
        
        # Check if code already exists
        code = request.POST.get('code')
        if code and MissionControle.objects.filter(code=code).exists():
            messages.error(request, "Ce code de mission existe déjà. Veuillez en choisir un autre.")
            return render(request, self.template_name, {
                'mission_form': mission_form,
                'error_message': 'Ce code de mission existe déjà. Veuillez en choisir un autre.'
            })

        if mission_form.is_valid():
            mission = mission_form.save(commit=False)
            mission.created_by = request.user
            mission.save()

            # Il ne peut y avoir qu’une seule gamme (selon le JS)
            intitule = request.POST.get('gamme_0_intitule')
            if intitule:
                statut = request.POST.get('gamme_0_statut') == 'True'
                version = request.POST.get('gamme_0_version', '1.0')

                no_incident = request.POST.get('gamme_0_no_incident', '')
                # Ensure gamme title follows the format 'Gamme: [Mission Title]' if it's empty or being reset
                if not intitule or intitule.strip() == '':
                    intitule = f"Gamme: {mission.intitule}"
                gamme = GammeControle.objects.create(
                    mission=mission,
                    intitule=intitule,
                    No_incident=no_incident,
                    statut=statut,
                    version=version,
                    created_by=request.user
                )

                # Lire toutes les opérations associées à cette gamme
                operation_index = 0
                while True:
                    titre = request.POST.get(f'operation_0_{operation_index}_titre')
                    if not titre:
                        break

                    ordre = request.POST.get(f'operation_0_{operation_index}_ordre', 0)
                    description = request.POST.get(f'operation_0_{operation_index}_description', '')
                    criteres = request.POST.get(f'operation_0_{operation_index}_criteres', '')

                    operation = OperationControle.objects.create(
                        gamme=gamme,
                        titre=titre,
                        ordre=ordre,
                        description=description,
                        criteres=criteres,
                        created_by=request.user
                    )

                    # Lire les photos associées à cette opération
                    photo_index = 0
                    while True:
                        image = request.FILES.get(f'photo_0_{operation_index}_{photo_index}_image')
                        if not image:
                            break

                        photo_description = request.POST.get(
                            f'photo_0_{operation_index}_{photo_index}_description', '')

                        PhotoOperation.objects.create(
                            operation=operation,
                            image=image,
                            description=photo_description,
                            created_by=request.user
                        )

                        photo_index += 1

                    operation_index += 1

            messages.success(request, "Mission, gamme, opérations et photos enregistrées avec succès.")
            return redirect('Gamme:missioncontrole_list')

        # Si formulaire invalide
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
        return render(request, self.template_name, {
            'mission_form': mission_form,
        })

class MissionControleListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = MissionControle
    template_name = 'gamme/missioncontrole_list.html'
    
    def test_func(self):
        # Only allow access if user is admin, responsable, or operator
        return self.request.user.is_authenticated
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Accès refusé. Vous n'avez pas les droits nécessaires.")
        return redirect('Gamme:dashboard')

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # For operators, only show active missions
        if self.request.user.is_op:
            queryset = queryset.filter(statut=True)
        else:
            # For admin/manager, apply filters if any
            statut = self.request.GET.get('statut')
            if statut == '1':
                queryset = queryset.filter(statut=True)
            elif statut == '0':
                queryset = queryset.filter(statut=False)
        
        # Apply product filter if provided
        produitref = self.request.GET.get('produitref')
        if produitref:
            queryset = queryset.filter(produitref__icontains=produitref)
            
        return queryset.order_by('-date_creation')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get unique product references for the filter dropdown
        produits = MissionControle.objects.values_list('produitref', flat=True).distinct()
        context['produits'] = sorted([p for p in produits if p and p.strip()])
        
        # Add filter values to context
        context['current_statut'] = self.request.GET.get('statut', '')
        context['current_produitref'] = self.request.GET.get('produitref', '')
        
        # Add user role to context for template logic
        context['is_operator'] = self.request.user.is_op
        
        return context

class MissionControleDeleteView(LoginRequiredMixin, DeleteView):
    model = MissionControle
    success_url = reverse_lazy('Gamme:missioncontrole_list')

class OperationControleCreateView(LoginRequiredMixin, View):
    template_name = 'gamme/operationcontrole_create.html'

    def get(self, request, *args, **kwargs):
        operation_form = OperationControleForm()
        return render(request, self.template_name, {
            'operation_form': operation_form,
        })

    def post(self, request, *args, **kwargs):
        operation_form = OperationControleForm(request.POST)

        if operation_form.is_valid():
            operation = operation_form.save(commit=False)
            operation.created_by = request.user
            operation.save()
            return redirect('Gamme:operationcontrole_list')
        
        return render(request, self.template_name, {
            'operation_form': operation_form,
        })

class OperationControleUpdateView(LoginRequiredMixin, UpdateView):
    model = OperationControle
    form_class = OperationControleForm
    template_name = 'gamme/operationcontrole_update.html'
    success_url = reverse_lazy('Gamme:operationcontrole_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['photos'] = PhotoOperation.objects.filter(operation=self.object).order_by('-id')
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

class OperationControleListView(ListView,LoginRequiredMixin):
    model = OperationControle
    template_name = 'gamme/operationcontrole_list.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        mission_id = self.kwargs.get('mission_id') or self.request.GET.get('mission')
        if mission_id:
            queryset = queryset.filter(mission_id=mission_id)
        return queryset.order_by('ordre')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mission_id = self.request.GET.get('mission')
        if mission_id:
            context['mission'] = get_object_or_404(MissionControle, pk=mission_id)
        return context

class OperationControleDeleteView(LoginRequiredMixin, DeleteView):
    model = OperationControle
    template_name = 'gamme/operationcontrole_delete.html'
    success_url = reverse_lazy('Gamme:operationcontrole_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if is_ajax:
            try:
                self.object.delete()
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
        else:
            success_url = self.get_success_url()
            self.object.delete()
            messages.success(request, "L'opération a été supprimée avec succès.")
            return redirect(success_url)

class OperationControleDetailView(DetailView,LoginRequiredMixin):
    model = OperationControle
    template_name = 'gamme/operationcontrole_detail.html'
    context_object_name = 'operation'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['photos'] = PhotoOperation.objects.filter(operation=self.object)
        if 'photo_form' not in context:
            context['photo_form'] = PhotoOperationForm()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

class PhotoOperationCreateView(LoginRequiredMixin,CreateView):
    model = PhotoOperation
    form_class = PhotoOperationForm
    template_name = None

    def form_valid(self, form):
        operation_id = self.request.POST.get('operation')
        form.instance.operation_id = operation_id
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        form.save()
        return redirect(reverse('Gamme:operationcontrole_update', kwargs={'pk': operation_id}))

    def get(self, request, *args, **kwargs):
        return redirect('Gamme:operationcontrole_list')

class PhotoOperationListView(LoginRequiredMixin, ListView):
    model = PhotoOperation
    template_name = 'gamme/photooperation_list.html'

    def get_queryset(self):
        return PhotoOperation.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['operations'] = OperationControle.objects.all()
        return context

class PhotoOperationUpdateView(LoginRequiredMixin,UpdateView):
    model = PhotoOperation
    form_class = PhotoOperationForm
    template_name = 'gamme/photooperation_update.html'

class PhotoOperationDeleteView(LoginRequiredMixin,DeleteView):
    model = PhotoOperation
    template_name = 'gamme/photooperation_delete.html'

    def get_success_url(self):
        return reverse_lazy('Gamme:operationcontrole_update', kwargs={'pk': self.object.operation.pk})




class OperatorDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'gamme/operateur_dashboard.html'
    
    def test_func(self):
        return self.request.user.is_op
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Accès refusé. Vous devez être un opérateur pour accéder à cette page.")
        return redirect('Gamme:dashboard')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Only show active missions to operators
        missions = MissionControle.objects.filter(statut=True)
        context['missions'] = missions
        context['missions_count'] = missions.count()
        context['active_missions_count'] = missions.count()  # Only active missions are shown
        return context


class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = 'gamme/user_list.html'
    context_object_name = 'users'
    
    def get_queryset(self):
        # Get all users who are either opérateur, responsable, or RO
        return User.objects.filter(
            is_op=True
        ) | User.objects.filter(
            is_rs=True
        ) | User.objects.filter(
            is_ro=True
        ).order_by('username')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_count'] = self.get_queryset().count()
        return context

class UserUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    fields = ['username', 'email', 'first_name', 'last_name']
    template_name = 'gamme/user_update.html'
    success_url = reverse_lazy('Gamme:user_list')

    def form_valid(self, form):
        user = form.save(commit=False)
        
        # Handle role selection
        role = self.request.POST.get('role')
        user.is_op = (role == 'op')
        user.is_rs = (role == 'rs')
        user.is_ro = (role == 'ro')
        
        user.save()
        messages.success(self.request, "L'utilisateur a été mis à jour avec succès.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        context['selected_role'] = 'op' if user.is_op else 'rs' if user.is_rs else 'ro' if user.is_ro else ''
        return context


class UserDeleteView(LoginRequiredMixin, DeleteView):
    model = User
    template_name = 'gamme/user_confirm_delete.html'
    success_url = reverse_lazy('Gamme:user_list')
    
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
            return redirect(self.success_url)
            
        messages.success(request, f"L'utilisateur {user.username} a été supprimé avec succès.")
        return super().delete(request, *args, **kwargs)

class UserDeleteView(LoginRequiredMixin,DeleteView):
    model = User
    template_name = 'gamme/user_delete.html'
    success_url = reverse_lazy('Gamme:user_list')



class ProfileView(LoginRequiredMixin, View):
    template_name = 'gamme/profile.html'

    def get(self, request, *args, **kwargs):
        form = ProfileUpdateForm(instance=request.user)
        return render(request, self.template_name, {'form': form, 'user': request.user})

    def post(self, request, *args, **kwargs):
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profil mis à jour avec succès.')
            return redirect('Gamme:profile')
        messages.error(request, 'Erreur lors de la mise à jour du profil.')
        return render(request, self.template_name, {'form': form, 'user': request.user})

class logoutView(LoginRequiredMixin, View):
    def get(self, request):
        logout(request)
        messages.success(request, 'Déconnexion réussie.')
        return redirect('Gamme:login')
    
    def post(self, request):
        logout(request)
        messages.success(request, 'Déconnexion réussie.')
        return redirect('Gamme:login')
class op_edit(LoginRequiredMixin, DetailView):
    model = MissionControle
    template_name = 'gamme/op_edit.html'
    context_object_name = 'mission'
class login(LoginView):
    template_name = 'gamme/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        if self.request.user.is_op:
            messages.info(self.request, 'Vous êtes connecté en tant qu\'opérateur.')
            return reverse_lazy('Gamme:operateur_dashboard')
        return reverse_lazy('Gamme:missioncontrole_list')
class RegisterView(CreateView):
    model = User
    form_class = RegisterForm
    template_name = 'gamme/register.html'
    success_url = reverse_lazy('Gamme:login')

    def form_valid(self, form):
        messages.success(self.request, "Inscription réussie.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Erreur dans le formulaire.")
        return self.render_to_response(self.get_context_data(form=form))
class ajouter_utilisateur(LoginRequiredMixin, CreateView):
    model = User
    form_class = RegisterForm
    template_name = 'gamme/ajouter_utilisateur.html'
    success_url = reverse_lazy('Gamme:user_list')
    
    def form_valid(self, form):
        # Save the user first
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password1'])
        
        # Handle role selection - explicitly set all role fields
        role = self.request.POST.get('role')
        print(f"Selected role: {role}")  # Debug log
        
        # Reset all roles first
        user.is_op = False
        user.is_rs = False
        user.is_ro = False
        
        # Set the selected role
        if role == 'op':
            user.is_op = True
            print("Setting role to Opérateur")  # Debug log
        elif role == 'rs':
            user.is_rs = True
            print("Setting role to Responsable")  # Debug log
        elif role == 'ro':
            user.is_ro = True
            print("Setting role to Responsable Opérationnel")  # Debug log
            
        user.save()
        print(f"User saved with is_op={user.is_op}, is_rs={user.is_rs}, is_ro={user.is_ro}")  # Debug log
        
        messages.success(self.request, "L'utilisateur a été créé avec succès.")
        return redirect('Gamme:user_list')
        
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial']['is_op'] = False
        kwargs['initial']['is_rs'] = False
        return kwargs



def view_gamme_pdf(request, mission_id):
    """View to display the gamme PDF for a specific mission."""
    mission = get_object_or_404(MissionControle, id=mission_id)
    
    # Get the most recent gamme for this mission
    gamme = mission.gammes.order_by('-date_creation').first()
    
    # Get operations for the most recent gamme, ordered by 'ordre'
    operations_list = []
    if gamme:
        operations_list = list(gamme.operationcontrole_set.all().order_by('ordre'))
    
    operations_dict = {}
    for i in range(1, 9): # Operations 1 to 8
        if i <= len(operations_list):
            op = operations_list[i-1]
            operations_dict[i] = {
                'description': op.description,
                'photos': op.photooperation_set.all()
            }
        else:
            operations_dict[i] = {
                'description': '',
                'photos': []
            }
    
    # Get the RS user (Responsable de Service)
    rs_user = User.objects.filter(is_rs=True).first()
    if not rs_user:
        rs_user = None
    # Get the RO user (Responsable Opérationnel)
    ro_user = User.objects.filter(is_ro=True).first()
    if not ro_user:
        ro_user = None
    
    # Ensure we have default values
    if rs_user is None:
        rs_user = request.user if request.user.is_authenticated else None
    if ro_user is None:
        ro_user = request.user if request.user.is_authenticated else None
    
    # Get PhotoDefaut objects for this gamme
    photo_defauts = []
    if gamme and hasattr(gamme, 'photodefaut_set'):
        photo_defauts = gamme.photodefaut_set.all().order_by('date_ajout')
    
    context = {
        'mission': mission,
        'gammecontrole': gamme,  # Add gamme object as gammecontrole for the template
        'operations': operations_dict,
        'title': f'Gamme - {mission.intitule}',
        'rs_user': rs_user,
        'ro_user': ro_user,
        'photo_defauts': photo_defauts,
        'static_defect_photos': [
            {'image_path': '1.jpg', 'title': 'Défaut de surface'},
            {'image_path': '2.jpg', 'title': 'Défaut d\'assemblage'},
            {'image_path': 'logo.jpg', 'title': 'Défaut de marquage'},
        ]
    }
    
    # Render the HTML view with jsPDF for client-side PDF generation
    return render(request, 'gamme/gamme_pdf.html', context)


import logging
import json
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['POST'])
@csrf_exempt
def upload_photo_defaut(request):
    """
    View to handle uploading defect photos for a gamme.
    Expected POST data:
    - gamme_id: ID of the gamme
    - photos: One or more image files
    - description: Optional description for the photos
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentication required'}, status=403)

    try:
        gamme_id = request.POST.get('gamme_id')
        description = request.POST.get('description', '')
        
        if not gamme_id:
            return JsonResponse({'success': False, 'error': 'Missing gamme_id'}, status=400)
            
        gamme = get_object_or_404(GammeControle, id=gamme_id)
        
        # Handle multiple file uploads
        files = request.FILES.getlist('photos')
        if not files:
            return JsonResponse({'success': False, 'error': 'No files provided'}, status=400)
        
        saved_photos = []
        for file in files:
            # Save the file using the storage API
            file_path = default_storage.save(f'photos/defaut_{gamme_id}_{file.name}', ContentFile(file.read()))
            
            # Create PhotoDefaut instance
            photo = PhotoDefaut.objects.create(
                gamme=gamme,
                image=file_path,
                description=description,
                created_by=request.user
            )
            saved_photos.append({
                'id': photo.id,
                'url': photo.image.url,
                'description': photo.description
            })
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully uploaded {len(saved_photos)} photos',
            'photos': saved_photos
        })
        
    except Exception as e:
        logger.error(f'Error uploading defect photos: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_http_methods(['POST'])
@csrf_exempt
def delete_photo_defaut(request, photo_id):
    """
    View to delete a defect photo.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentication required'}, status=403)
    
    try:
        photo = get_object_or_404(PhotoDefaut, id=photo_id)
        gamme_id = photo.gamme.id
        
        # Delete the file from storage
        if photo.image:
            photo.image.delete(save=False)
            
        # Delete the database record
        photo.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Photo deleted successfully',
            'gamme_id': gamme_id
        })
        
    except Exception as e:
        logger.error(f'Error deleting defect photo: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def save_mission_pdf(request, mission_id):
    """View to save an uploaded PDF file to the MissionControle model.
    
    This view expects a POST request with a file in the 'pdf_file' field.
    The file should be a PDF generated client-side using jsPDF.
    """
    logger.info(f"=== SAVE MISSION PDF REQUEST ===")
    logger.info(f"URL: {request.path}")
    logger.info(f"Method: {request.method}")
    logger.info(f"Content-Type: {request.content_type}")
    
    # Only allow POST requests
    if request.method != 'POST':
        logger.error(f"Method {request.method} not allowed for this endpoint")
        return JsonResponse(
            {'success': False, 'error': f'Method {request.method} not allowed'}, 
            status=405,
            headers={'Allow': 'POST'}
        )
    
    # Check if the request is multipart/form-data
    if not request.content_type.startswith('multipart/form-data'):
        logger.error(f"Invalid content type: {request.content_type}")
        return JsonResponse(
            {'success': False, 'error': 'Content-Type must be multipart/form-data'},
            status=400
        )
    
    # Check if file was uploaded
    if 'pdf_file' not in request.FILES:
        logger.error("No file part in the request")
        return JsonResponse(
            {'success': False, 'error': 'No file part'},
            status=400
        )
    
    try:
        # Get the mission object
        mission = get_object_or_404(MissionControle, id=mission_id)
        logger.info(f"Processing mission: {mission.id} - {mission.intitule}")
        
        # Get the uploaded file
        pdf_file = request.FILES['pdf_file']
        logger.info(f"Received file: {pdf_file.name}, size: {pdf_file.size} bytes, content_type: {pdf_file.content_type}")
        
        # Validate file type
        if not pdf_file.name.lower().endswith('.pdf') or 'pdf' not in pdf_file.content_type.lower():
            logger.error(f"Invalid file type: {pdf_file.content_type}")
            return JsonResponse(
                {'success': False, 'error': 'File must be a PDF'},
                status=400
            )
        
        # Delete old file if exists
        if mission.pdf_file:
            try:
                mission.pdf_file.delete(save=False)
                logger.info("Deleted old PDF file")
            except Exception as e:
                logger.warning(f"Could not delete old file: {str(e)}")
        
        # Save the new file
        file_name = f'mission_{mission.id}_gamme.pdf'
        mission.pdf_file.save(file_name, pdf_file, save=True)
        
        logger.info(f"Successfully saved PDF to {mission.pdf_file.path}")
        
        return JsonResponse({
            'success': True,
            'message': 'PDF uploaded and saved successfully',
            'pdf_url': request.build_absolute_uri(mission.pdf_file.url)
        })
        
    except Exception as e:
        logger.error(f"Error saving PDF: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

