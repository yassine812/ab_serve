from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Max, Prefetch
import os
import logging
import json
from django.views.generic import ListView,DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.forms import inlineformset_factory
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import MissionControle, GammeControle, OperationControle, PhotoOperation, PhotoDefaut, User, epi, moyens_controle
from .forms import MissionControleForm, GammeControleForm,ProfileUpdateForm, OperationControleForm,OperationControleFormSet, PhotoOperationForm, UpdateGammeFormSet, UpdateOperationFormSet, UpdatePhotoFormSet,RegisterForm, EpiForm, MoyenControleForm
from django.contrib.auth import logout
from django.views import View
from django.contrib.auth.views import LoginView
import logging
import json
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
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
        
        # Get all gammes with their operations, regardless of status
        gammes = GammeControle.objects.filter(mission=missioncontrole).prefetch_related(
            Prefetch('operations', queryset=OperationControle.objects.all().prefetch_related(
                Prefetch('moyenscontrole', queryset=moyens_controle.objects.all().order_by('ordre')), 
                'photooperation_set'
            )), 
            'defaut_photos',
            'epis',  # Prefetch EPIs for each gamme
            'moyens_controle'  # Prefetch moyens_controle for each gamme
        ).order_by('-date_mise_a_jour')
        
        # Add a flag to each gamme to indicate if it's active and calculate next order
        for gamme in gammes:
            gamme.is_active = gamme.statut
            # Calculate next order number based on current gamme's operations
            max_order = gamme.operations.aggregate(Max('ordre'))['ordre__max']
            if max_order is not None:
                gamme.next_order = (int(max_order) - 1) + 1  # This simplifies to just max_order
            else:
                gamme.next_order = 1
        
        # Get moyens de contrôle ordered by 'ordre'
        moyens_controle_list = moyens_controle.objects.all().order_by('ordre')
        
        # Get all EPIs
        all_epis = epi.objects.all()
        
        context = {
            'missioncontrole': missioncontrole,
            'gammes': gammes,
            'operation_formset': operation_formset,
            'moyens_controle': moyens_controle_list,
            'epis': all_epis,
        }
        
        return render(request, self.template_name, context)

    def post(self, request, pk):
        missioncontrole = get_object_or_404(MissionControle, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            # --- Mise à jour des champs mission ---
            missioncontrole.code = request.POST.get('code', missioncontrole.code)
            missioncontrole.intitule = request.POST.get('intitule', missioncontrole.intitule)
            missioncontrole.reference = request.POST.get('reference', missioncontrole.reference)
            missioncontrole.statut = request.POST.get('statut', str(missioncontrole.statut)) == 'True'
            missioncontrole.client = request.POST.get('client', missioncontrole.client or '')
            missioncontrole.designation = request.POST.get('designation', missioncontrole.designation or '')
            missioncontrole.section = request.POST.get('section', missioncontrole.section or '')
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
                processed_op_ids = set()
                for op in gamme.operations.all():
                    if op.id in processed_op_ids:
                        continue  # Skip already processed operations
                    processed_op_ids.add(op.id)
                    
                    titre = request.POST.get(f"{op.id}-titre", op.titre)
                    ordre = request.POST.get(f"{op.id}-ordre", op.ordre)
                    description = request.POST.get(f"{op.id}-description", op.description)
                    criteres = request.POST.get(f"{op.id}-criteres", op.criteres)

                    if titre != op.titre or str(ordre) != str(op.ordre) or description != op.description or criteres != op.criteres:
                        changement_detecte = True
                        # Update the operation in place if no new gamme is being created
                        if not changement_detecte:
                            op.titre = titre
                            op.ordre = ordre
                            op.description = description
                            op.criteres = criteres
                            op.save()

                    # Process existing photos
                    for photo in op.photooperation_set.all():
                        desc = request.POST.get(f"photo_{photo.id}_description", photo.description)
                        delete = request.POST.get(f"photo_{photo.id}_DELETE", None)
                        if desc != photo.description or delete is not None:
                            changement_detecte = True
                            # Update photo in place if no new gamme is being created
                            if not changement_detecte and desc != photo.description:
                                photo.description = desc
                                photo.save()

                    # Check for new dynamic photos
                    has_new_photos = any(key.startswith(f'photo_{op.id}_') for key in request.FILES.keys())
                    if has_new_photos:
                        changement_detecte = True

                # Check for changes in moyens de contrôle
                selected_moyens_ids = set([k.split('_')[-1] for k in request.POST.keys() if k.startswith(f'gamme_{gamme.id}_moyen_controle_') and request.POST.get(k) == 'on'])
                current_moyens_ids = set([str(m.id) for m in gamme.moyens_controle.all()])
                if selected_moyens_ids != current_moyens_ids:
                    changement_detecte = True

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
                    # Get the latest version number
                    latest_version = float(gamme.version) if gamme.version else 1.0
                    next_version = round(latest_version + 0.1, 1)
                    
                    # First, check if we already have an inactive version with this version number
                    existing_version = GammeControle.objects.filter(
                        mission=missioncontrole,
                        intitule=gamme.intitule,
                        version=str(next_version)
                    ).exists()
                    
                    # Only proceed if we don't already have this version
                    if not existing_version:
                        with transaction.atomic():
                            # Mark all versions of this gamme as inactive
                            GammeControle.objects.filter(
                                mission=missioncontrole, 
                                intitule=gamme.intitule,
                                statut=True  # Only mark active versions as inactive
                            ).update(statut=False)
                            
                            # Mark the current gamme as inactive
                            gamme.statut = False
                            gamme.save()
                    else:
                        # Skip creating a new version if it already exists
                        continue

                    no_incident = request.POST.get(f'{gamme.id}-No_incident', gamme.No_incident)
                    # Get the new fields
                    commentaire = request.POST.get(f'{gamme.id}-commentaire', gamme.commantaire or '')
                    temps_alloue = request.POST.get(f'{gamme.id}-temps_alloue', gamme.Temps_alloué)
                    commentaire_identification = request.POST.get(f'{gamme.id}-commentaire_identification', gamme.commantaire_identification or '')
                    commentaire_non_conforme = request.POST.get(f'{gamme.id}-commentaire_non_conforme', gamme.commantaire_traitement_non_conforme or '')
                    
                    # Handle file upload for photo_non_conforme
                    photo_non_conforme = request.FILES.get(f'{gamme.id}-photo_non_conforme')
                    if not photo_non_conforme and hasattr(gamme, 'photo_traitement_non_conforme'):
                        photo_non_conforme = gamme.photo_traitement_non_conforme
                    
                    picto_s = request.POST.get(f'{gamme.id}-picto_s') == 'on'
                    picto_r = request.POST.get(f'{gamme.id}-picto_r') == 'on'
                    
                    # Create new gamme with statut=True
                    new_gamme = GammeControle.objects.create(
                        mission=missioncontrole,
                        intitule=intitule,
                        No_incident=no_incident,
                        statut=True,  # Explicitly set to True for the new version
                        version=next_version,
                        commantaire=commentaire,
                        Temps_alloué=temps_alloue if temps_alloue else None,
                        commantaire_identification=commentaire_identification,
                        commantaire_traitement_non_conforme=commentaire_non_conforme,
                        photo_traitement_non_conforme=photo_non_conforme,
                        picto_s=picto_s,
                        picto_r=picto_r,
                        created_by=request.user
                    )

                    # Save selected moyens de contrôle for the new gamme
                    moyen_controle_ids = [k.split('_')[-1] for k in request.POST.keys()
                                       if k.startswith(f'gamme_{gamme.id}_moyen_controle_') and request.POST.get(k) == 'on']
                    if moyen_controle_ids:
                        selected_moyens = moyens_controle.objects.filter(id__in=moyen_controle_ids)
                        new_gamme.moyens_controle.set(selected_moyens)

                    # Save selected EPIs for the new gamme
                    epi_ids = [k.split('_')[-1] for k in request.POST.keys()
                             if k.startswith(f'gamme_{gamme.id}_epi_') and request.POST.get(k) == 'on']
                    if epi_ids:
                        selected_epis = epi.objects.filter(id__in=epi_ids)
                        new_gamme.epis.set(selected_epis)

                    # Update EPI comments if submitted
                    for key, value in request.POST.items():
                        if key.startswith('epi_') and key.endswith('_commentaire'):
                            try:
                                epi_id = int(key.split('_')[1])
                                epi_obj = epi.objects.get(id=epi_id)
                                if epi_obj.commentaire != value:
                                    epi_obj.commentaire = value
                                    epi_obj.save()
                                    print(f"Updated commentaire for EPI {epi_obj.nom} (ID: {epi_obj.id})")
                            except (ValueError, epi.DoesNotExist) as e:
                                print(f"Error updating EPI comment for key {key}: {e}")

                # If we're creating a new gamme version, we'll create new operations for it
                if changement_detecte and new_gamme != gamme:
                    # Get the maximum order value from existing operations in the new gamme
                    max_order = OperationControle.objects.filter(gamme=new_gamme).aggregate(Max('ordre'))['ordre__max'] or 0
                    
                    # First, collect all operations with their new order values
                    operations_to_update = []
                    processed_op_ids = set()  # Track processed operation IDs to prevent duplicates
                    
                    # Process existing operations
                    for op in gamme.operations.all():
                        if op.id in processed_op_ids:
                            continue  # Skip already processed operations
                            
                        processed_op_ids.add(op.id)
                        
                        # Get the new values from the form
                        new_titre = request.POST.get(f"{op.id}-titre", op.titre)
                        new_description = request.POST.get(f"{op.id}-description", op.description)
                        new_criteres = request.POST.get(f"{op.id}-criteres", op.criteres)
                        new_ordre = request.POST.get(f"{op.id}-ordre")
                        
                        try:
                            new_ordre = int(new_ordre) if new_ordre is not None else op.ordre
                        except (ValueError, TypeError):
                            new_ordre = op.ordre
                        
                        # Get the moyen_controle value from the form or use the existing one
                        moyen_controle_value = request.POST.get(f"{op.id}-moyen_controle", '')
                        if not moyen_controle_value and hasattr(op, 'moyen_controle'):
                            moyen_controle_value = op.moyen_controle
                        
                        # Only add the operation if it belongs to the current gamme version
                        if op.gamme_id == gamme.id:
                            operations_to_update.append({
                                'op': op,
                                'new_order': new_ordre,
                                'titre': new_titre,
                                'description': new_description or '',
                                'criteres': new_criteres or '',
                                'frequence': request.POST.get(f"{op.id}-frequence", getattr(op, 'frequence', 1)),
                                'moyens_id': request.POST.get(f"{op.id}-moyens"),
                                'moyenscontrole': op.moyenscontrole.all(),
                                'moyen_controle': moyen_controle_value
                            })
                else:
                    # If no new gamme version, update operations in place
                    for op in gamme.operations.all():
                        if op.id in processed_op_ids:
                            continue
                            
                        processed_op_ids.add(op.id)
                        
                        # Get the new values from the form
                        new_titre = request.POST.get(f"{op.id}-titre", op.titre)
                        new_description = request.POST.get(f"{op.id}-description", op.description)
                        new_criteres = request.POST.get(f"{op.id}-criteres", op.criteres)
                        new_ordre = request.POST.get(f"{op.id}-ordre")
                        
                        try:
                            new_ordre = int(new_ordre) if new_ordre is not None else op.ordre
                        except (ValueError, TypeError):
                            new_ordre = op.ordre
                        
                        # Update the operation in place
                        op.titre = new_titre
                        op.description = new_description
                        op.criteres = new_criteres
                        op.ordre = new_ordre
                        
                        # Update moyen_controle if needed
                        moyen_controle_value = request.POST.get(f"{op.id}-moyen_controle")
                        if moyen_controle_value:
                            op.moyen_controle = moyen_controle_value
                        
                        op.save()
                        
                        # Handle photos for the operation
                        self._handle_operation_photos(request, op)

                    # Save selected moyens de contrôle for the new gamme
                    moyen_controle_ids = [k.split('_')[-1] for k in request.POST.keys()
                                       if k.startswith(f'gamme_{gamme.id}_moyen_controle_') and request.POST.get(k) == 'on']
                    if moyen_controle_ids:
                        selected_moyens = moyens_controle.objects.filter(id__in=moyen_controle_ids)
                        gamme.moyens_controle.set(selected_moyens)
                        
                    # Skip the rest of the operation creation logic for existing gamme
                    continue
                
                # Sort operations by their new order to ensure consistent ordering
                operations_to_update.sort(key=lambda x: x['new_order'])
                
                # Now create the operations in the new gamme with their new order values
                current_order = 1
                for op_data in operations_to_update:
                    # Ensure the order is unique and sequential
                    while OperationControle.objects.filter(gamme=new_gamme, ordre=current_order).exists():
                        current_order += 1
                    
                    # Get moyen de contrôle if selected
                    moyen = None
                    if op_data['moyens_id']:
                        try:
                            moyen = moyens_controle.objects.get(id=op_data['moyens_id'])
                        except (moyens_controle.DoesNotExist, ValueError):
                            pass
                    
                    # Create the new operation with all fields except many-to-many
                    new_op = OperationControle.objects.create(
                        gamme=new_gamme,
                        titre=op_data['titre'],
                        ordre=current_order,  # Use the sequential order
                        description=op_data['description'],
                        criteres=op_data['criteres'],
                        frequence=op_data['frequence'],
                        moyen_controle=op_data['moyen_controle'],
                        created_by=request.user
                    )
                    
                    # Set moyen de contrôle if selected using set() for many-to-many
                    if moyen:
                        new_op.moyenscontrole.set([moyen])
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
                    frequence = request.POST.get(f'newop_{gamme.id}_{i}_frequence', '')
                    moyen_controle = request.POST.get(f'newop_{gamme.id}_{i}_moyen_controle', '')
                    
                    # Get the next available order value for this gamme
                    max_ordre = OperationControle.objects.filter(
                        gamme=new_gamme
                    ).aggregate(Max('ordre'))['ordre__max'] or 0
                    next_ordre = max_ordre + 1
                    
                    print(f"Creating new operation with ordre: {next_ordre} for gamme {new_gamme.id}")
                    
                    # Create the new operation with all fields including moyen_controle
                    new_op = OperationControle.objects.create(
                        gamme=new_gamme,
                        titre=titre,
                        ordre=next_ordre,  # Use the calculated next order
                        description=description,
                        criteres=criteres,
                        frequence=frequence,
                        moyen_controle=moyen_controle,
                        created_by=request.user
                    )
                    
                    # Get and set moyens de contrôle for this new operation
                    moyens_ids = request.POST.getlist(f'newop_{gamme.id}_{i}_moyens')
                    if moyens_ids:
                        try:
                            moyen = moyens_controle.objects.get(id=moyens_ids[0])  # Assuming single selection
                            new_op.moyenscontrole = moyen
                            new_op.save()
                        except (moyens_controle.DoesNotExist, ValueError):
                            pass

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
            # Debug: Print all POST data
            print("\n=== DEBUG: RAW POST DATA ===")
            for key, value in request.POST.items():
                print(f"{key}: {value}")
                
            # Handle picto values
            picto_combined = request.POST.get('gamme_picto_combined', 'R')
            picto_s = 'S' in picto_combined
            picto_r = 'R' in picto_combined
            
            # Create the new gamme with all form fields
            new_gamme = GammeControle.objects.create(
                mission=missioncontrole,
                intitule=gamme_intitule,
                No_incident=gamme_no_incident,
                statut=gamme_statut == 'True',
                commantaire=request.POST.get('gamme_commantaire', ''),
                Temps_alloué=request.POST.get('gamme_Temps_alloue'),  # Note the accented 'é'
                commantaire_identification=request.POST.get('gamme_commantaire_identification', ''),
                commantaire_traitement_non_conforme=request.POST.get('gamme_commantaire_traitement_non_conforme', ''),
                picto_s=picto_s,
                picto_r=picto_r,
                created_by=request.user,
                version='1.0'  # Version is a CharField in the model
            )
            
            # Handle photo upload for traitement non conforme
            if 'gamme_photo_traitement_non_conforme' in request.FILES:
                new_gamme.photo_traitement_non_conforme = request.FILES['gamme_photo_traitement_non_conforme']
                new_gamme.save()
            
            # Debug: Print all EPI and moyen checkboxes
            print("\n=== DEBUG: EPI CHECKBOXES ===")
            for k, v in request.POST.items():
                if k.startswith('gamme_epi_') or k.startswith('gamme_moyen_controle_'):
                    print(f"{k}: {v}")
            
            # Debug: Print all POST data for EPI and moyens de contrôle
            print("\n=== DEBUG: RAW POST DATA FOR CHECKBOXES ===")
            for k, v in request.POST.items():
                if k.startswith('gamme_epi_') or k.startswith('gamme_moyen_controle_'):
                    print(f"{k}: {v}")
            
            # Handle EPI selections - check for any EPI checkboxes that were checked
            epi_ids = []
            for k, v in request.POST.items():
                if k.startswith('gamme_epi_'):
                    try:
                        # Get the EPI ID from the checkbox name (format: gamme_epi_<id>)
                        epi_id = int(k.split('_')[-1])
                        # The value is the EPI ID, not 'on' like in some forms
                        epi_ids.append(epi_id)
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing EPI ID from {k}: {e}")
            
            print(f"Found EPI IDs: {epi_ids}")
            new_gamme.epis.set(epi_ids)
            
            # Handle moyens de contrôle selections - check for any moyen checkboxes that were checked
            moyen_ids = []
            for k, v in request.POST.items():
                if k.startswith('gamme_moyen_controle_'):
                    try:
                        # Get the moyen ID from the checkbox name (format: gamme_moyen_controle_<id>)
                        moyen_id = int(k.split('_')[-1])
                        # The value is the moyen ID, not 'on' like in some forms
                        moyen_ids.append(moyen_id)
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing moyen ID from {k}: {e}")
            
            print(f"Found moyen IDs: {moyen_ids}")
            new_gamme.moyens_controle.set(moyen_ids)
            
            # Debug: Print all form data with more details
           
            print("\n=== FORM DATA ===")
            for key, value in request.POST.items():
                print(f"{key}: {value}")
            
            print("\n=== FILES ===")
            for key, file_obj in request.FILES.items():
                print(f"{key}: {file_obj.name} (size: {file_obj.size} bytes, type: {file_obj.content_type})")
            
            # Print all request headers for debugging
           
                        # Process operation forms using Django formset
            operation_formset = OperationControleFormSet(
                request.POST, 
                request.FILES,
                prefix='form',
                queryset=OperationControle.objects.none()
            )
            
           
            
            
            if operation_formset.is_valid():
                operations = operation_formset.save(commit=False)
                
                
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
                    
                    # Process moyen de contrôle for this operation
                    # Get the moyen_controle value from the form
                    moyen_controle_value = request.POST.get(f'form-{i}-moyen_controle', '').strip()
                    if moyen_controle_value:
                        operation.moyen_controle = moyen_controle_value
                        print(f"  - Set moyen de contrôle: {moyen_controle_value}")
                    
                    # Process the many-to-many relationship if it exists
                    if hasattr(operation, 'moyens_controle'):
                        # Clear existing moyens de contrôle first
                        operation.moyens_controle.clear()
                        
                        # Find all selected moyens de contrôle for this operation
                        for key, value in request.POST.items():
                            if key.startswith(f'op_{operation.id}_moyen_') and value == 'on':
                                try:
                                    moyen_id = int(key.split('_')[-1])
                                    moyen = moyens_controle.objects.get(id=moyen_id)
                                    operation.moyens_controle.add(moyen)
                                    print(f"  - Added moyen de contrôle: {moyen.nom} (ID: {moyen.id})")
                                except (ValueError, moyens_controle.DoesNotExist) as e:
                                    print(f"  - Error adding moyen de contrôle: {e}")
                        
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
        epis = epi.objects.all().order_by('nom')
        return render(request, self.template_name, {
            'form': form,
            'missions': missions,
            'epis': epis
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


from django.db import transaction

class MissionControleCreateView(LoginRequiredMixin,View):
    template_name = 'gamme/missioncontrole_create.html'

    def get(self, request):
        mission_form = MissionControleForm()
        moyens_list = moyens_controle.objects.all().order_by('ordre')
        epis_list = epi.objects.all()
        
        return render(request, self.template_name, {
            'mission_form': mission_form,
            'moyens_controle': moyens_list,
            'epis': epis_list,
        })

    def post(self, request):
        print("\n=== Form Submission Started ===")
        print("=== POST data ===")
        for key, value in request.POST.items():
            print(f"{key}: {value}")
            
        print("\n=== FILES data ===")
        for key, file in request.FILES.items():
            print(f"{key}: {file.name} ({file.size} bytes)")
        
        # Create form instance with request data
        mission_form = MissionControleForm(request.POST, request.FILES)
        
        print("\n=== Form Validation ===")
        
        # Check if code already exists first
        code = request.POST.get('code')
        if code and MissionControle.objects.filter(code=code).exists():
            print("Code already exists")
            messages.error(request, "Ce code de mission existe déjà. Veuillez en choisir un autre.")
            
            # Prepare form data for repopulation
            form_data = {}
            for key, value in request.POST.lists():
                if len(value) == 1:
                    form_data[key] = value[0]
                else:
                    form_data[key] = value
            
            # Add file data
            for key, file in request.FILES.items():
                form_data[key] = file.name
            
            context = {
                'mission_form': mission_form,
                'moyens_controle': moyens_controle.objects.all().order_by('ordre'),
                'epis': epi.objects.all(),
                'form_data_json': json.dumps(form_data, ensure_ascii=False, default=str),
                'form_errors': {'code': ['Ce code de mission existe déjà.']}
            }
            return render(request, self.template_name, context)
        
        # Validate the form
        if not mission_form.is_valid():
            print("Form errors:", mission_form.errors)
            
            # Print each field's value for debugging
            print("\n=== Form Data ===")
            for field in mission_form:
                print(f"{field.name}:")
                print(f"  Value: {field.value()}")
                print(f"  Errors: {field.errors}")
                print(f"  Required: {field.field.required}")
                print(f"  Field type: {field.field.__class__.__name__}")
                print(f"  Widget: {field.field.widget.__class__.__name__}")
                
                if hasattr(mission_form, 'cleaned_data') and field.name in mission_form.cleaned_data:
                    print(f"  Cleaned data: {mission_form.cleaned_data[field.name]}")
                print()
            
            # Prepare form data for repopulation
            form_data = {}
            for key, value in request.POST.lists():
                if len(value) == 1:
                    form_data[key] = value[0]
                else:
                    form_data[key] = value
            
            # Add file data
            for key, file in request.FILES.items():
                form_data[key] = file.name
            
            # Convert form errors to a format that's easy to display in the template
            form_errors = {}
            for field_name, errors in mission_form.errors.items():
                form_errors[field_name] = errors
            
            context = {
                'mission_form': mission_form,
                'moyens_controle': moyens_controle.objects.all().order_by('ordre'),
                'epis': epi.objects.all(),
                'form_data_json': json.dumps(form_data, ensure_ascii=False, default=str),
                'form_errors': form_errors  # Pass form errors to template
            }
            
            # Add error messages for each field with errors
            for field_name, errors in form_errors.items():
                for error in errors:
                    messages.error(request, f"{field_name}: {error}")
            
            return render(request, self.template_name, context)

        print("Mission form is valid. Attempting to save mission...")
        try:
            mission = mission_form.save(commit=False)
            mission.created_by = request.user
            mission.save()
            print(f"Mission saved successfully. ID: {mission.id}, Code: {mission.code}")

            # Process each gamme
            gamme_index = 0
            while True:
                # Check if gamme exists in POST data
                intitule_key = f'gamme_{gamme_index}_intitule'
                if intitule_key not in request.POST:
                    print(f"No more gammes found at index {gamme_index}")
                    break  # No more gammes
                    
                # Check if we have a valid gamme with required fields
                intitule = request.POST.get(intitule_key, '').strip()
                if not intitule:
                    print(f"Skipping empty gamme at index {gamme_index}")
                    gamme_index += 1
                    continue

                # Extract other gamme fields
                statut = request.POST.get(f'gamme_{gamme_index}_statut') == 'True'
                version = request.POST.get(f'gamme_{gamme_index}_version', '1.0')
                no_incident = request.POST.get(f'gamme_{gamme_index}_no_incident', '')
                commentaire = request.POST.get(f'gamme_{gamme_index}_commentaire', '')
                temps_alloue_str = request.POST.get(f'gamme_{gamme_index}_temps_alloue')
                temps_alloue = int(temps_alloue_str) if temps_alloue_str else None
                commentaire_identification = request.POST.get(f'gamme_{gamme_index}_commentaire_identification', '')
                commentaire_traitement_non_conforme = request.POST.get(f'gamme_{gamme_index}_commentaire_traitement_non_conforme', '')
                photo_traitement_non_conforme = request.FILES.get(f'gamme_{gamme_index}_photo_traitement_non_conforme')
                picto_s = f'gamme_{gamme_index}_picto_s' in request.POST
                picto_r = f'gamme_{gamme_index}_picto_r' in request.POST

                if not intitule:
                    messages.error(request, f"Gamme {gamme_index + 1}: L'intitulé est obligatoire.")
                    gamme_index += 1
                    continue

                if not no_incident:
                    messages.error(request, f"Gamme {gamme_index + 1}: Le numéro d'incident est obligatoire.")
                    gamme_index += 1
                    continue

                # Check if statut is provided and is a valid boolean representation
                if statut is None:
                    messages.error(request, f"Gamme {gamme_index + 1}: Le statut est obligatoire.")
                    gamme_index += 1
                    continue

                # Ensure gamme title follows the format 'Gamme: [Mission Title]' if it's empty or being reset
                if not intitule or intitule.strip() == '':
                    intitule = f"Gamme: {mission.intitule}"

                print(f"Processing Gamme {gamme_index}:")
                print(f"  Intitule: {intitule}")
                print(f"  Statut: {statut}")
                print(f"  Version: {version}")
                print(f"  No Incident: {no_incident}")
                print(f"  Commentaire: {commentaire}")
                print(f"  Temps Alloue: {temps_alloue}")
                print(f"  Commentaire Identification: {commentaire_identification}")
                print(f"  Commentaire Traitement Non Conforme: {commentaire_traitement_non_conforme}")
                print(f"  Photo Traitement Non Conforme: {photo_traitement_non_conforme}")
                print(f"  Picto S: {picto_s}, Picto R: {picto_r}")

                try:
                    gamme = GammeControle.objects.create(
                        mission=mission,
                        intitule=intitule,
                        No_incident=no_incident,
                        statut=statut,
                        version=version,
                        commantaire=commentaire,
                        Temps_alloué=temps_alloue,
                        commantaire_identification=commentaire_identification,
                        commantaire_traitement_non_conforme=commentaire_traitement_non_conforme,
                        photo_traitement_non_conforme=photo_traitement_non_conforme,
                        picto_s=picto_s,
                        picto_r=picto_r,
                        created_by=request.user
                    )
                    print(f"Gamme created successfully. ID: {gamme.id}, Intitule: {gamme.intitule}")

                    # Save selected moyens de contrôle
                    moyen_controle_ids = request.POST.getlist(f'gamme_{gamme_index}_moyen_controle')
                    print(f"Gamme {gamme_index} - Moyen Controle IDs: {moyen_controle_ids}")
                    if moyen_controle_ids:
                        selected_moyens = moyens_controle.objects.filter(id__in=moyen_controle_ids)
                        gamme.moyens_controle.set(selected_moyens)

                    # Save selected EPIs
                    epi_ids = [v for k, v in request.POST.items()
                             if k.startswith(f'gamme_{gamme_index}_epi_') and v != '']
                    print(f"Gamme {gamme_index} - EPI IDs: {epi_ids}")
                    print(f"  All EPI values: {[(k, v) for k, v in request.POST.items() if k.startswith(f'gamme_{gamme_index}_epi_')]}")
                    for epi_id in epi_ids:
                        try:
                            epi_item = epi.objects.get(id=epi_id)
                            gamme.epis.add(epi_item)
                            print(f"  - Added EPI to gamme: {epi_item.nom} (ID: {epi_item.id})")
                        except epi.DoesNotExist:
                            messages.error(request, f"EPI avec l'ID {epi_id} non trouvé pour gamme {gamme_index + 1}.")
                            print(f"  - EPI avec l'ID {epi_id} non trouvé pour gamme")
                        except Exception as e:
                            messages.error(request, f"Erreur lors de l'ajout de l'EPI {epi_id} à la gamme {gamme_index + 1}: {str(e)}")
                            print(f"  - Erreur lors de l'ajout de l'EPI {epi_id} à la gamme: {str(e)}")

                except Exception as e:
                    messages.error(request, f"Erreur lors de la création de la gamme {gamme_index + 1}: {str(e)}")
                    print(f"Error creating gamme {gamme_index + 1}: {str(e)}")
                    gamme_index += 1
                    continue
                    
                # Only increment gamme_index if we successfully processed a gamme
                print(f"Successfully processed gamme {gamme_index + 1}, incrementing index...")
                
                # Store the current gamme index for processing its operations
                current_gamme_idx = gamme_index 
                gamme_index += 1

                # Process operations for the current gamme
                operation_index = 0
                print(f"Processing operations for gamme {current_gamme_idx}...")
                while True:
                    op_titre_key = f'operation_formset-{current_gamme_idx}-{operation_index}_titre'
                    op_titre = request.POST.get(op_titre_key)
                    
                    print(f"Checking operation {operation_index} with key {op_titre_key}")
                    
                    if not op_titre:
                        print(f"No operation found at index {operation_index}, ending operation processing for this gamme")
                        break

                    # Use current_gamme_idx instead of gamme_index for operation form fields
                    op_ordre = request.POST.get(f'operation_formset-{current_gamme_idx}-{operation_index}_ordre', 0)
                    op_description = request.POST.get(f'operation_formset-{current_gamme_idx}-{operation_index}_description', '')
                    op_criteres = request.POST.get(f'operation_formset-{current_gamme_idx}-{operation_index}_criteres', '')
                    op_moyen_controle_text = request.POST.get(f'operation_formset-{current_gamme_idx}-{operation_index}_moyen_controle', '')
                    op_frequence_str = request.POST.get(f'operation_formset-{gamme_index}-{operation_index}_frequence', '')
                    op_frequence = int(op_frequence_str) if op_frequence_str.isdigit() else 1 # Default to 1 if not a valid number

                    if not op_titre:
                        messages.error(request, f"Opération {operation_index + 1} de la gamme {gamme_index + 1}: Le titre est obligatoire.")
                        operation_index += 1
                        continue

                    try:
                        # Check if an operation with this order already exists for this gamme
                        existing_operation = OperationControle.objects.filter(
                            gamme=gamme,
                            ordre=op_ordre
                        ).first()
                        
                        if existing_operation:
                            # Update existing operation
                            existing_operation.titre = op_titre
                            existing_operation.description = op_description
                            existing_operation.criteres = op_criteres
                            existing_operation.moyen_controle = op_moyen_controle_text
                            existing_operation.frequence = op_frequence
                            existing_operation.save()
                            operation = existing_operation
                            print(f"Updated existing operation. ID: {operation.id}, Titre: {operation.titre}")
                        else:
                            # Create new operation
                            operation = OperationControle.objects.create(
                                gamme=gamme,
                                titre=op_titre,
                                ordre=int(op_ordre),
                                description=op_description,
                                criteres=op_criteres,
                                moyen_controle=op_moyen_controle_text,
                                frequence=op_frequence,
                                created_by=request.user,
                            )
                            print(f"Operation created successfully. ID: {operation.id}, Titre: {operation.titre}")
                        print(f"Operation created successfully. ID: {operation.id}, Titre: {operation.titre}")
                    except Exception as e:
                        messages.error(request, f"Erreur lors de la création de l'opération {operation_index + 1} de la gamme {gamme_index + 1}: {str(e)}")
                        operation_index += 1
                        continue
                    # Save selected moyens de contrôle for the operation
                    op_moyen_controle_ids = request.POST.getlist(f'operation_formset-{current_gamme_idx}-{operation_index}_moyens_controle')
                    if op_moyen_controle_ids:
                        selected_moyens = moyens_controle.objects.filter(id__in=op_moyen_controle_ids)
                        operation.moyenscontrole.set(selected_moyens)

                    # Process photos for the current operation
                    photo_index = 0
                    while True:
                        photo_file_key = f'photo_{current_gamme_idx}_{operation_index}_{photo_index}_image'
                        photo_image = request.FILES.get(photo_file_key)

                        if not photo_image:
                            # No more photos to process for this operation
                            break

                        photo_description = request.POST.get(f'photo_{current_gamme_idx}_{operation_index}_{photo_index}_description', '')
                        print(f"Processing Photo {photo_index} for Operation {operation.id}:")
                        print(f"  File Key: {photo_file_key}")
                        print(f"  Description: {photo_description}")

                        try:
                            photo = PhotoOperation.objects.create(
                                operation=operation,
                                image=photo_image,
                                description=photo_description,
                                created_by=request.user
                            )
                            print(f"Photo created successfully. ID: {photo.id}, Description: {photo.description}")
                        except Exception as e:
                            print(f"Error creating photo: {str(e)}")
                            messages.error(request, f"Erreur lors de la création de la photo {photo_index + 1} de l'opération {operation_index + 1} de la gamme {current_gamme_idx + 1}: {str(e)}")
                        
                        # Always increment the photo index to prevent infinite loop
                        photo_index += 1
                        
                        # Safety check to prevent infinite loops
                        if photo_index > 100:  # Reasonable upper limit
                            print("Warning: Reached maximum number of photos per operation (100)")
                            break
                    
                    # Move to next operation
                    operation_index += 1

            print("=== Form Submission Completed Successfully ===")
            messages.success(request, "Mission, gammes, opérations et photos enregistrées avec succès.")
            return redirect('Gamme:missioncontrole_list')

        except Exception as e:
            print("=== Form Submission Failed ===")
            print("Error:", str(e))
            if not mission_form.is_valid():
                print("Form errors:", mission_form.errors)
            messages.error(request, f"Une erreur est survenue: {str(e)}")
            
            # Convert QueryDict to regular dict for JSON serialization
            form_data = {}
            for key, value in request.POST.lists():
                if len(value) == 1:
                    form_data[key] = value[0]
                else:
                    form_data[key] = value
            
            # Add file data
            for key, file in request.FILES.items():
                form_data[key] = file.name  # Just store the filename for display
            
            # Prepare context with form data as JSON
            context = {
                'mission_form': mission_form,
                'moyens_controle': moyens_controle.objects.all().order_by('ordre'),
                'epis': epi.objects.all(),
                'form_data_json': json.dumps(form_data, ensure_ascii=False)
            }
            return render(request, self.template_name, context)

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
        reference = self.request.GET.get('reference')
        if reference:
            queryset = queryset.filter(reference__icontains=reference)
            
        return queryset.order_by('-date_creation')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get unique product references for the filter dropdown
        references = MissionControle.objects.values_list('reference', flat=True).distinct()
        context['references'] = sorted([r for r in references if r and r.strip()])
        
        # Add filter values to context
        context['current_statut'] = self.request.GET.get('statut', '')
        context['current_reference'] = self.request.GET.get('reference', '')
        
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


class EpiCreateView(LoginRequiredMixin, CreateView):
    model = epi
    template_name = 'gamme/epi_form.html'
    fields = ['nom', 'photo', 'commentaire']
    success_url = reverse_lazy('Gamme:epi_list')
    
    def form_valid(self, form):
        messages.success(self.request, "L'équipement de protection a été créé avec succès.")
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Ajouter un équipement de protection'
        context['submit_text'] = 'Créer'
        return context


class EpiListView(LoginRequiredMixin, ListView):
    model = epi
    template_name = 'gamme/epi_list.html'
    context_object_name = 'object_list'
    paginate_by = 10
    
    def get_queryset(self):
        return epi.objects.all().order_by('nom')


class EpiUpdateView(LoginRequiredMixin, UpdateView):
    model = epi
    form_class = EpiForm
    template_name = 'gamme/epi_update.html'
    success_url = reverse_lazy('Gamme:epi_list')
    
    def form_valid(self, form):
        messages.success(self.request, "L'équipement de protection a été mis à jour avec succès.")
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Modifier {self.object.nom}"
        return context
    
    def get_success_url(self):
        return reverse_lazy('Gamme:epi_list')


class EpiDeleteView(LoginRequiredMixin, DeleteView):
    model = epi
    template_name = 'gamme/epi_confirm_delete.html'
    success_url = reverse_lazy('Gamme:epi_list')
    
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.photo:
            self.object.photo.delete(save=False)
        response = super().delete(request, *args, **kwargs)
        messages.success(request, "L'équipement de protection a été supprimé avec succès.")
        return response


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
        
        # Reset all roles first
        user.is_op = False
        user.is_rs = False
        user.is_ro = False
        
        # Set the selected role
        if role == 'op':
            user.is_op = True
        elif role == 'rs':
            user.is_rs = True
        elif role == 'ro':
            user.is_ro = True
            
        user.save()
        
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
        print(f"\n=== DEBUG: GAMME FOUND - ID: {gamme.id}, TITLE: {gamme.intitule} ===")
        operations_list = list(gamme.operations.all().order_by('ordre').prefetch_related('moyenscontrole'))
        print(f"Number of operations: {len(operations_list)}")
    else:
        print("\n=== DEBUG: NO GAMME FOUND FOR THIS MISSION ===")
    
    operations_dict = {}
    # Get unique moyens_controle directly from the gamme
    unique_moyens = set()
    
    if gamme:
        # Get moyens_controle directly from the gamme
        gamme_moyens = list(gamme.moyens_controle.all())  # Using the correct field name with underscore
        print(f"\n=== DEBUG: MOYENS FROM GAMME ===")
        print(f"Number of moyens in gamme: {len(gamme_moyens)}")
        for m in gamme_moyens:
            unique_moyens.add(m)
            print(f"  Moyen: ID={m.id}, Nom='{m.nom}', Photo={bool(m.photo)}")
    else:
        print("\n=== DEBUG: NO GAMME FOUND TO GET MOYENS FROM ===")
    
    for i in range(1, 9): # Operations 1 to 8
        if i <= len(operations_list):
            op = operations_list[i-1]
            op_moyens = list(op.moyenscontrole.all())
            print(f"\nOperation {i} - ID: {op.id}, Description: {op.description}")
            print(f"Number of moyens for operation {i}: {len(op_moyens)}")
            
            operations_dict[i] = {
                'description': op.description,
                'photos': op.photooperation_set.all(),
                'moyenscontrole': op_moyens,
                'frequence': op.frequence,
                'moyen_controle': op.moyen_controle
            }
        else:
            operations_dict[i] = {
                'description': '',
                'photos': [],
                'moyenscontrole': [],
                'frequence': '',
                'moyen_controle': ''
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
    
    # Format the allocated time with a default value if not set
    temps_alloue = ''
    if gamme and hasattr(gamme, 'Temps_alloué') and gamme.Temps_alloué is not None:
        temps_alloue = str(gamme.Temps_alloué)
    
    # Convert set to list and sort by ordre
    unique_moyens_list = sorted(unique_moyens, key=lambda x: x.ordre if hasattr(x, 'ordre') else 0)
    
    # Debug: Print the unique moyens to console
    print(f"Unique moyens to display: {[m.nom for m in unique_moyens_list]}")
    
    # Get EPIs for the gamme
    epis = []
    if gamme:
        epis = list(gamme.epis.all())
        print(f"EPIs to display: {[e.nom for e in epis]}")
    
    context = {
        'mission': mission,
        'gammecontrole': gamme,
        'operations': operations_dict,
        'unique_moyens': unique_moyens_list,  # Add unique moyens to context
        'title': f'Gamme - {mission.intitule}',
        'rs_user': rs_user,
        'ro_user': ro_user,
        'photo_defauts': photo_defauts,
        'temps_alloue': temps_alloue,
        'static_defect_photos': [
            {'image_path': '1.jpg', 'title': 'Défaut de surface'},
            {'image_path': '2.jpg', 'title': 'Défaut d\'assemblage'},
            {'image_path': 'logo.jpg', 'title': 'Défaut de marquage'},
        ],
        'epis': epis  # Add EPIs to the context
    }
    
    # Render the HTML view with jsPDF for client-side PDF generation
    return render(request, 'gamme/gamme_pdf.html', context)




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

class MoyenControleListView(LoginRequiredMixin, ListView):
    model = moyens_controle
    template_name = 'gamme/moyenscontrole_list.html'
    context_object_name = 'object_list'
    paginate_by = 10
    
    def get_queryset(self):
        return moyens_controle.objects.all().order_by('ordre', 'nom')


class MoyenControleCreateView(LoginRequiredMixin, CreateView):
    model = moyens_controle
    form_class = MoyenControleForm
    template_name = 'gamme/moyenscontrole_create.html'
    
    def get_success_url(self):
        messages.success(self.request, "Le moyen de contrôle a été créé avec succès.")
        return reverse('Gamme:moyencontrole_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Ajouter un moyen de contrôle'
        return context


class MoyenControleUpdateView(LoginRequiredMixin, UpdateView):
    model = moyens_controle
    form_class = MoyenControleForm
    template_name = 'gamme/moyenscontrole_update.html'
    
    def get_success_url(self):
        messages.success(self.request, "Le moyen de contrôle a été mis à jour avec succès.")
        return reverse('Gamme:moyencontrole_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Modifier {self.object.nom}"
        return context


class MoyenControleDeleteView(LoginRequiredMixin, DeleteView):
    model = moyens_controle
    template_name = 'gamme/moyenscontrole_delete.html'
    
    def get_success_url(self):
        messages.success(self.request, "Le moyen de contrôle a été supprimé avec succès.")
        return reverse('Gamme:moyencontrole_list')
    
    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        return response


from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import MissionControle, validation, OperationControle
from django.db import transaction

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def validate_gamme(request, gamme_id):
    """
    API endpoint to validate a gamme by creating a single validation record for the entire gamme.
    """
    try:
        # Get the gamme
        from .models import GammeControle
        gamme = get_object_or_404(GammeControle, id=gamme_id)
        
        # Create a single validation record for the gamme
        with transaction.atomic():
            # Update gamme status to validated
            gamme.statut = True
            gamme.save()
            
            # Create a validation record for the gamme
            validation.objects.create(
                gamme=gamme,
                user_ro=request.user,
                date_validation_user_ro=timezone.now(),
                commentaire=f"Gamme validée le {timezone.now().strftime('%d/%m/%Y à %H:%M')}"
            )
        
        return JsonResponse({
            'success': True, 
            'message': 'Gamme validée avec succès !',
            'gamme_id': gamme.id,
            'validated_at': timezone.now().strftime('%d/%m/%Y à %H:%M'),
            'validated_by': request.user.get_full_name() or request.user.username
        })
        
    except Exception as e:
        logger.error(f"Error validating gamme {gamme_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def check_mission_code(request):
    code = request.GET.get('code', None)
    if code is not None:
        exists = MissionControle.objects.filter(code=code).exists()
        return JsonResponse({'exists': exists})
    return JsonResponse({'exists': False})



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
