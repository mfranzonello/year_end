'''Functions to interact with Adobe Premiere Pro via pymiere.'''

import subprocess
from time import sleep

import pymiere

from structure import COLOR_LABELS, ADOBE_BIN
from system import file_type, mount_premiere

ITEM_TYPES = {1: 'CLIP', 2: 'BIN', 3: 'ROOT', 4: 'FILE'}
ITEM_COLORS = ['Violet', 'Iris', 'Caribbean', 'Lavender',
               'Cerulean', 'Forest', 'Rose', 'Mango',
               'Purple', 'Blue', 'Teal', 'Magenta',
               'Tan', 'Green', 'Brown', 'Yellow']

PREMIERE_LOCATION = r"C:\Program Files\Adobe\Adobe Premiere Pro 2025\Adobe Premiere Pro.exe"

## project.consolidateDuplicates()
## TODO: move videos in the wrong bins

def open_premiere():
    '''Ensure Premiere Pro is running.'''
    premiere_open = False

    while not premiere_open:
        try:
            premiere_open = pymiere.objects.app
        except ValueError:
            print('Starting Premiere Pro...')
            mount_premiere()
            sleep(20) # wait for Premiere to open

def open_project(path):
    '''Open a Premiere project file.'''

    # ensure Premiere is running
    open_premiere()

    # make sure it's a valid project
    if file_type(path) != 'PREMIERE_PROJECT' or not(pymiere.objects.app.isDocument(str(path))):
        print(f'Not a document: {path}')

    else:
        # check open projects
        project_id = None
        if pymiere.objects.app.projects.numProjects:
            print('Checking open projects...')
            # find the project, if open
            for i, proj in enumerate(pymiere.objects.app.projects):
                if proj.path == str(path):
                    project_id = i
                    continue

        # open project if not already open
        if not project_id:
            print(f'Trying to open {str(path)}')
            pymiere.objects.app.openDocument(str(path))
            # assign last position as current project
            project_id = pymiere.objects.app.projects.numProjects - 1

        return project_id

def find_videos_bin(project_id):
    '''Find the "Videos" bin in the project.'''
    for p_item in pymiere.objects.app.projects[project_id].rootItem.children:
        if ITEM_TYPES[p_item.type] == 'BIN' and p_item.name == ADOBE_BIN:
            return p_item

def find_person_bin(videos_bin, name):
    '''Find a bin for a person in the videos bin.'''
    for child in videos_bin.children:
        if ITEM_TYPES[child.type] == 'BIN' and child.name == name:
            return child

def create_person_bin(videos_bin, name):
    '''Create a bin for a person in the videos bin.'''
    videos_bin.createBin(name)

def create_person_bins(videos_bin, names):
    '''Create bins for each person in the videos bin if not existing.'''
    existing_bins = [child.name for child in videos_bin.children if ITEM_TYPES[child.type] == 'BIN']
    for name in names:
        if name not in existing_bins:
            create_person_bin(videos_bin, name)

def get_color_label(project_item):
    '''Get the existing color index of a project item.'''
    return project_item.getColorLabel()

def set_color_label(project_item, color):
    '''Set the color index of a project item if different.'''
    if project_item.getColorLabel != color:
        project_item.setColorLabel(color)

def get_family_color_label(name: str) -> int | None:
    '''Returns the index position of the family dictionary whose 'members' list contains the given name.'''
    for i, fam in enumerate(COLOR_LABELS):
        if name in fam.get("members", []):
            return i

def set_family_color_labels(videos_bin):
    '''Set color labels for clips in person bins based on family membership.'''
    for c_bin in videos_bin.children:
        if ITEM_TYPES[c_bin.type] == 'BIN':
            family_color_label = get_family_color_label(c_bin.name)
            if family_color_label:
                for c_item in c_bin.children:
                    if ITEM_TYPES[c_item.type] == 'CLIP':
                        set_color_label(c_item, family_color_label)

def import_videos(project_id, videos_bin, person_name, file_list):
    importable_videos = [str(file_path) for file_path in file_list if not videos_bin.findItemsMatchingMediaPath(str(file_path), ignoreSubclips=1).length]
    skipped_imports = len(file_list) - len(importable_videos)

    if skipped_imports == len(file_list):
        print('\t\tSkipping, all rated videos already imported.')
    elif skipped_imports:
        v_s = 's' if skipped_imports != 1 else ''
        print(f'\t\tSkipping {skipped_imports} already imported video{v_s}...')

    if importable_videos:
        '''Import videos into the person's bin in Premiere.'''
        v_s = 's' if skipped_imports != 1 else ''
        print(f'\t\tImporting {len(importable_videos)} video{v_s}...')
        person_bin = find_person_bin(videos_bin, person_name)
        if person_bin:
            import_success = pymiere.objects.app.project.importFiles(arrayOfFilePathsToImport=importable_videos,
                                                                     suppressUI=False, targetBin=person_bin, importAsNumberedStills=False)
        return import_success