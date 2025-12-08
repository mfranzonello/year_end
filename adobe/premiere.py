'''Functions to interact with Adobe Premiere Pro via pymiere.'''

from time import sleep
from pathlib import Path
import gzip
import xml.etree.ElementTree as ET

import pymiere

from common.console import SplitConsole
from common.structure import ADOBE_BIN, write_json, PR_LABEL_EX
from common.system import file_type, mount_premiere

ITEM_TYPES = {1: 'CLIP', 2: 'BIN', 3: 'ROOT', 4: 'FILE'}

## TODO:
## projectitem.getMediaPath()
## project.consolidateDuplicates()
# # app.project.rootItem.children[index].getProjectColumnsMetadata() -> 'Video Usage'

# see what's already used
def convert_to_xml(project_path:Path) -> ET.Element|None:
    if file_type(project_path) == 'PREMIERE_PROJECT':
        with gzip.open(project_path, 'rb') as f:
            xml_content = f.read()

        return ET.fromstring(xml_content)

def extract_included_video_paths(root:ET.Element) -> list[str]:
    # returns all videos already imported into the project
    master_clips_urefs = [v.find('MediaSource').find('Media').get('ObjectURef')
                          for v in root.findall('VideoMediaSource')]
    media_paths = [m.find('RelativePath').text for m in root.findall('Media')
                   if m.get('ObjectUID') in master_clips_urefs and m.find('RelativePath') is not None]

    return media_paths

def extract_used_video_paths(root:ET.Element) -> list[str]:
    # returns all videos actually used in the timeline
    clip_refs = [c.find('Clip').get('ObjectRef') for c in root.findall('SubClip')]
    subbed_clips = [c for c in root.findall('VideoClip') if c.get('ObjectID') in clip_refs]
    source_refs = set(c.find('Clip').find('Source').get('ObjectRef') for c in subbed_clips)
    master_clips_urefs = [v.find('MediaSource').find('Media').get('ObjectURef')
                          for v in root.findall('VideoMediaSource') if v.get('ObjectID') in source_refs]
    media_paths = [m.find('RelativePath').text for m in root.findall('Media')
                   if m.get('ObjectUID') in master_clips_urefs and m.find('RelativePath') is not None]

    return media_paths

# bring new items into Premiere
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
            pymiere.objects.app.openDocument(str(path),
                                             suppressConversionDialog=True,
                                             bypassLocateFileDialog=True,
                                             bypassWarningDialog=True,
                                             doNotAddToMRUList=True)
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
    if get_color_label(project_item) != color:
        project_item.setColorLabel(color)

def set_family_color_labels(videos_bin, label_map):
    '''Set color labels for clips in person bins based on family membership.'''
    for c_bin in videos_bin.children:
        if ITEM_TYPES[c_bin.type] == 'BIN':
            family_color_label = label_map.get(c_bin.name)
            if family_color_label:
                for c_item in c_bin.children:
                    if ITEM_TYPES[c_item.type] == 'CLIP':
                        set_color_label(c_item, family_color_label)

def check_video_in_bin(videos_bin, video_path:Path):
    return videos_bin.findItemsMatchingMediaPath(str(video_path), ignoreSubclips=1).length > 0

def import_videos(project_id, videos_bin, person_name:str, import_file_list:list[Path], ui:SplitConsole, dry_run=True):
    import_success = False

    person_bin = find_person_bin(videos_bin, person_name)

    # videos that should be in this bin
    importable_videos = [p for p in import_file_list if not check_video_in_bin(videos_bin, p)]
    # videos that already exist in this bin
    existing_videos = [p for p in import_file_list if check_video_in_bin(person_bin, p)]
    # videos that already exist in another bin
    movable_videos = [p for p in existing_videos if not check_video_in_bin(person_bin, p)]

    skipped_imports = len(existing_videos) - (len(importable_videos) + len(movable_videos))

    if skipped_imports > 0:
        v_s = 's' if skipped_imports != 1 else ''
        ui.set_status(f'Skipping {skipped_imports} already imported video{v_s}...')

    if importable_videos:
        # import videos into the person's bin in Premiere
        v_s = 's' if len(importable_videos) != 1 else ''
        ui.add_update(f'Importing {len(importable_videos)} video{v_s}...')
        person_bin = find_person_bin(videos_bin, person_name)
        if person_bin:
            if not dry_run:
                import_success = pymiere.objects.app.project.importFiles(arrayOfFilePathsToImport=[str(p) for p in importable_videos],
                                                                         suppressUI=False, targetBin=person_bin, importAsNumberedStills=False)

    if movable_videos:
        v_s = 's' if len(movable_videos) != 1 else ''
        ui.add_update(f'Moving {len(movable_videos)} video{v_s} to {person_name} bin...')
        for file_path in movable_videos:
            for item in videos_bin.findItemsMatchingMediaPath(str(file_path), ignoreSubclips=1):
                if not dry_run:
                    item.moveBin(person_bin)

    return import_success

def hex_to_rgb(color_hex):
    r = int(color_hex[1:3], 16)
    g = int(color_hex[3:5], 16)
    b = int(color_hex[5:7], 16)
    return (r, g, b)

def create_label_presets(color_labels, common_folder, label_preset_name):
    color_labels.loc[:, ['r', 'g', 'b']] = color_labels.apply(lambda x: hex_to_rgb(x['color_hex']), axis=1, result_type='expand').values
    label_presets = {'colors': [{'color': {'b': row['b'],
                                           'g': row['g'],
                                           'r': row['r']},
                                 'name': row['label_name']} for _, row in color_labels.iterrows()],
                     'defaults': {'audio': 14, 'bin': 7, 'captions': 7, 'dynamiclink': 6, 'movie': 1, 'sequence': 5, 'still': 3, 'video': 15}
                     }

    write_json(common_folder, label_preset_name, label_presets, ext=PR_LABEL_EX)

    return label_presets

def get_sequence_maps(project_id):
    vals = [(s.name, s.projectItem.nodeId, i) for i, s in enumerate(pymiere.objects.app.projects[project_id].sequences)]
    sequence_map_by_name = {n: i for n, _, i in vals}
    sequence_map_by_node = {n: i for _, n, i in vals}
    return sequence_map_by_name, sequence_map_by_node

def get_sequence(project_id, sequence_id):
    return pymiere.objects.app.projects[project_id].sequences[sequence_id]

def get_actors_in_sequence(sequence_item, project_id, sequence_map,
                           seq_start=0, seq_in=0, seq_out=0, ## should also be looking just at things after in and before out
                           banned_bins=[], banned_nodes=[]): 
    print(f'Looking in sequence {sequence_item.name}...')
    actor_appearances = []

    if not seq_out:
        seq_out = sequence_item.end / 254016000000

    for v_track in sequence_item.videoTracks:
        for clip in v_track.clips:

            # check if clip has visible video
            if clip.projectItem and not clip.disabled:
                project_item = clip.projectItem

                # check if this is automatically ruled out
                if not any(project_item.treePath.startswith(f'\\{pymiere.objects.app.projects[project_id].name}\\{b}\\') for b in banned_bins):

                    # check if item is in visible timeline
                    if not(clip.start.seconds >= seq_out or clip.end.seconds < seq_in):
                        start_time = seq_start + max(seq_in, clip.start.seconds)
                        end_time = seq_start + min(seq_out, clip.end.seconds)

                        # check if sequence that hasn't been ruled out
                        if project_item.isSequence() and project_item.nodeId not in banned_nodes:
                            next_sequence_item = get_sequence(project_id, sequence_map[project_item.nodeId])
                            actor_subappearances = get_actors_in_sequence(next_sequence_item, project_id, sequence_map,
                                                                            seq_start=start_time + clip.inPoint.seconds,
                                                                            seq_in=clip.inPoint.seconds, seq_out=clip.outPoint.seconds,
                                                                            banned_bins=banned_bins, banned_nodes=banned_nodes)
                            if not actor_subappearances:
                                # there are no appearances in here, so don't check again
                                banned_nodes.append(project_item.nodeId)

                            else:
                                # this sequence has appearances
                                actor_appearances.extend(actor_subappearances)

                        else:
                            # actual video content potentially with actors
                            metadata = project_item.getProjectMetadata()
                            actor_field = 'ActorUUID'
                            premiere_private = 'premierePrivateProjectMetaData'
                            searchword = f'<{premiere_private}:{actor_field}>'
                            if searchword in metadata:
                                actor_uuids = metadata[metadata.find(searchword)+len(searchword):
                                                       metadata.find(searchword.replace('<', '</'))].split(',')
                                actor_appearances.append({'actor_uuid': actor_uuids,
                                                          'start_time': round(start_time, 2),
                                                          'end_time': round(end_time, 2)})

    return actor_appearances

def get_actors_in_project(project_id, sequence_name, sequence_map_by_name, sequence_map_by_node, banned_bins=[]):
    print(f'Pulling up main sequence')

    if sequence_name in sequence_map_by_name:
        sequence_item = get_sequence(project_id, sequence_map_by_name.get(sequence_name))
        return get_actors_in_sequence(sequence_item, project_id, sequence_map_by_node, banned_bins=banned_bins)

def get_chapter_markers(project_id, sequence_name, sequence_map_by_name):
    print('Getting chapter markers')

    if sequence_name in sequence_map_by_name:
        sequence = pymiere.objects.app.projects[project_id].sequences[sequence_map_by_name[sequence_name]]
        markers = sequence.markers
        
        n_markers = markers.numMarkers
        if n_markers:
            chapters = []
            marker = markers.getFirstMarker()
            for i in range(n_markers):
                if marker.type == 'Chapter':
                    chapters.append((marker.name, round(marker.start.seconds, 2)))

                if i < n_markers - 1:
                    marker = markers.getNextMarker(marker)

            return chapters