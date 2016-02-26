import os

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from mpf.migrator.migrator import VersionMigrator
from mpf.core.rgb_color import named_rgb_colors, RGBColor

from mpf.file_interfaces.yaml_interface import YamlInterface


class V4Migrator(VersionMigrator):

    config_version = 4

    # These sections are in the order they're processed

    renames = '''
    - old: sound_system|initial_volume
      new: master_volume
    - old: tocks_per_sec
      new: speed
    - old: fonts
      new: text_styles
    - old: movies
      new: videos
    '''

    moves = '''
    - old: window|frame
      new: window|borderless
    - old: window|quit_on_close
      new: window|exit_on_escape
    '''

    deprecations = '''
    - timing
    - plugins
    - sound_system|volume_steps
    - sound_system|stream
    - window|elements|__list__|pixel_spacing*
    - window|fps

    # everything from here down is old than v3, but I saw them in some configs
    # so figured we can get rid of them now too
    - machine_flow
    - machineflow
    '''
    
    additions = '''
    sound_system:
      enabled: True
    '''

    warnings = dict(
        pixel_spacing="""Setting Removed:
    The virtual DMD "pixel_spacing" key was removed, as there now more
    options to finely-tune the look of the pixels. Your spacing is now set
    to the default. Check the docs for details of the new options.""",
                    )

    slides = dict()
    displays = dict()
    default_display = None
    WIDTH = 800
    HEIGHT = 600

    def __init__(self, file_name, file_contents):
        super().__init__(file_name, file_contents)
        self.created_slide_player = False

    @classmethod
    def _get_slide_name(cls, display):
        if display not in cls.slides:
            cls.slides[display] = 0

        cls.slides[display] += 1

        if display:
            return '{}_slide_{}'.format(display, cls.slides[display])
        else:
            return 'slide_{}'.format(cls.slides[display])

    @classmethod
    def _add_display(cls, name, w, h):
        cls.log.debug("Detected display '%s' (%sx%s)", name, w, h)
        cls.displays[name] = (w, h)

    def _do_custom(self):
        # This runs last, so items will be in their new / renamed locations
        self._migrate_window()
        self._create_display_from_dmd()
        self._migrate_physical_dmd()
        self._migrate_slide_player()
        self._create_window_slide()
        self._migrate_sound_system()
        self._migrate_fonts()
        self._migrate_asset_defaults()
        self._migrate_migrate_animation_assets()
        self._migrate_assets('images')
        self._migrate_assets('videos')
        self._migrate_assets('sounds')

    def _migrate_window(self):
        # Create a display from the window
        if 'window' in self.fc:
            self.log.debug("Converting window: section")
            if 'displays' not in self.fc:
                self.fc['displays'] = CommentedMap()
            self.fc['displays']['window'] = CommentedMap()

            self.fc['displays']['window']['height'] = self.fc['window']['height']
            self.fc['displays']['window']['width'] = self.fc['window']['width']
            self._add_display('window', self.fc['window']['width'],
                              self.fc['window']['height'])
            V4Migrator.default_display = 'window'

            try:  # old setting was 'frame', so we need to flip it
                self.fc['window']['borderless'] = not self.fc['window']['borderless']
            except KeyError:
                pass

    def _create_display_from_dmd(self):
        if 'dmd' in self.fc:
            self.log.debug("Converting dmd: to displays:dmd:")
            if 'displays' not in self.fc:
                self.log.debug("Creating 'displays:' section")
                self.fc['displays'] = CommentedMap()

            V4Migrator.default_display = 'dmd'

            self.log.debug("Creating 'displays:dmd: section")
            self.fc['displays']['dmd'] = CommentedMap()

            self.fc['displays']['dmd'].update(self.fc['dmd'])
            self._add_display('dmd', self.fc['dmd']['width'],
                              self.fc['dmd']['height'])

    def _migrate_physical_dmd(self):
        if ('dmd' in self.fc and 'physical' in self.fc['dmd'] and
                self.fc['dmd']['physical']):

            self.log.debug("Converting physical dmd: settings")

            YamlInterface.del_key_with_comments(self.fc['dmd'] , 'physical',
                                                self.log)
            YamlInterface.del_key_with_comments(self.fc['dmd'] , 'fps',
                                                self.log)

            if 'type' in self.fc['dmd'] and self.fc['dmd']['type'] == 'color':
                # physical color DMD
                YamlInterface.del_key_with_comments(self.fc['dmd'] , 'type',
                                                self.log)
                YamlInterface.rename_key('dmd', 'physical_rgb_dmd', self.fc,
                                         self.log)

            else:  # physical mono DMD
                YamlInterface.del_key_with_comments(self.fc['dmd'] , 'type',
                                                self.log)
                YamlInterface.del_key_with_comments(self.fc['dmd'] , 'shades',
                                                self.log)

                YamlInterface.rename_key('dmd', 'physical_dmd', self.fc,
                                         self.log)

            YamlInterface.del_key_with_comments(self.fc['displays']['dmd'],
                                                'physical', self.log)
            YamlInterface.del_key_with_comments(self.fc['displays']['dmd'],
                                                'shades', self.log)
            YamlInterface.del_key_with_comments(self.fc['displays']['dmd'],
                                                'fps', self.log)

    def _migrate_slide_player(self):
        if 'slide_player' in self.fc:
            self.log.debug("Converting slide_player: entries to slides:")

            self.fc['slides'] = CommentedMap()
            new_slide_player = CommentedMap()

            for event, elements in self.fc['slide_player'].items():
                self.log.debug("Converting '%s' display_elements to widgets",
                               event)

                display = None
                transition = None

                # see if there's a display set
                for element in elements:
                    if 'display' in element:
                        self.log.debug("Converting display: to target:")
                        display = element['display']
                        del element['display']
                    if 'transition' in element:
                        transition = (element['transition'],
                                      element.ca.items.get('transition', None))
                        del element['transition']

                elements = self._migrate_elements(elements, display)

                slide = self._get_slide_name(display)

                new_slide_player[event] = CommentedMap()
                self.log.debug("Adding slide:%s to slide_player:%s", slide,
                               event)
                new_slide_player[event]['slide'] = slide

                if transition:
                    self.log.debug("Moving transition: from slide: to "
                                   "slide_player:")
                    new_slide_player[event]['transition'] = transition[0]
                    new_slide_player[event].ca.items['transition'] = (
                        transition[1])

                if display:
                    self.log.debug("Setting slide_player:target: to '%s'",
                                   display)
                    new_slide_player[event]['target'] = display

                self.log.debug("Creating slide: '%s' with %s migrated "
                               "widget(s)", slide, len(elements))
                self.fc['slides'][slide] = elements

            self.fc['slide_player'] = new_slide_player

    def _create_window_slide(self):
        if 'window' in self.fc and 'elements' in self.fc['window']:
            elements = self.fc['window']['elements']

            if isinstance(elements, dict):
                elements = [elements]

            if 'slides' not in self.fc:
                self.log.debug("Creating 'slides:' section")
                self.fc['slides'] = CommentedMap()

            slide_name = self._get_slide_name('window')

            self.log.debug("Creating slide: %s with %s display widget(s) from "
                           "the old window: config", slide_name, len(elements))

            self.log.debug("Adding '%s' slide", slide_name)
            self.fc['slides'][slide_name] = CommentedMap()
            self.fc['slides'][slide_name] = (
                self._migrate_elements(elements, 'window'))

            YamlInterface.del_key_with_comments(self.fc['window'], 'elements',
                                                self.log)

            if 'slide_player' not in self.fc:
                self.fc['slide_player'] = CommentedMap()
                self.log.debug("Creating slide_player: section")

            self.log.debug("Creating slide_player:machine_reset_phase3: entry"
                           "to show slide '%s' on boot", slide_name)
            self.fc['slide_player']['machine_reset_phase_3'] = CommentedMap()
            self.fc['slide_player']['machine_reset_phase_3'][
                'slide'] = slide_name
            self.fc['slide_player']['machine_reset_phase_3'][
                'target'] = 'window'

    def _migrate_sound_system(self):
        # convert stream track to regular track
        try:
            stream_track_name = self.fc['sound_system']['stream']['name']
            self.fc['sound_system']['tracks'][stream_track_name] = (
                CommentedMap())
            self.fc['sound_system']['tracks'][stream_track_name]['volume'] = 0.5
            self.fc['sound_system']['tracks'][stream_track_name][
                 'simultaneous_sounds'] = 1
            self.log.debug('Converting stream: audio track to normal track')
        except KeyError:
            pass

        try:
            old_buffer = self.fc['sound_system']['buffer']
        except KeyError:
            old_buffer = None

        try:
            self.fc['sound_system']['buffer'] = 2048
            if old_buffer:
                self.fc['sound_system'].yaml_add_eol_comment(
                    'previous value was {}'.format(old_buffer), 'buffer')
                self.log.debug("Setting sound_system:buffer: to '2048'. "
                               "(Was %s)", old_buffer)
        except KeyError:
            pass

    def _migrate_fonts(self):
        # Fonts to text_styles was already renamed, now update contents
        if 'text_styles' in self.fc:
            self.log.debug("Converting text_styles: from the old fonts: "
                           "settings")
            for settings in self.fc['text_styles'].values():
                YamlInterface.rename_key('size', 'font_size', settings, self.log)
                YamlInterface.rename_key('file', 'font_name', settings, self.log)

                if 'font_name' in settings:
                    self.log.debug("Converting font_name: from file to name")
                    settings['font_name'] = os.path.splitext(
                        settings['font_name'])[0]

    def _migrate_asset_defaults(self):
        # convert asset_defaults to assets:
        if 'asset_defaults' in self.fc:
            self.log.debug('Renaming key: asset_defaults -> assets:')
            YamlInterface.rename_key('asset_defaults', 'assets', self.fc, self.log)

            assets = self.fc['assets']

            if 'animations' in assets:
                self.log.debug("Converting assets:animations to assets:images")
                if 'images' in assets:
                    self.log.debug("Merging animations: into current "
                                   "asset:images:")
                    YamlInterface.copy_with_comments(assets, 'animations',
                                                     assets, 'images',
                                                     True, self.log)
                else:
                    YamlInterface.rename_key('animations', 'images', assets,
                                             self.log)
                YamlInterface.del_key_with_comments(self.fc, 'animations',
                                                    self.log)

            if 'movies' in assets:
                YamlInterface.rename_key('movies', 'videos', assets, self.log)

            if 'images' in assets:
                self.log.debug("Converting assets:images:")

                for settings in assets['images'].values():
                    YamlInterface.del_key_with_comments(settings, 'target',
                                                        self.log)

            if 'sounds' in assets:
                self.log.debug("Converting assets:sounds:")

                for asset, settings in assets['sounds'].items():
                    pass  # todo

    def _migrate_migrate_animation_assets(self):
        if 'animations' in self.fc:
            self.log.debug("Converting assets:animations to assets:images")
            if 'images' in self.fc:
                self.log.debug("Merging animations: into current "
                                   "asset:images:")

                YamlInterface.copy_with_comments(self.fc, 'animations',
                                                 self.fc, 'images',
                                                 True, self.log)

            else:
                YamlInterface.rename_key('animations', 'images', self.fc,
                                         self.log)

    def _migrate_assets(self, section_name):
        if section_name in self.fc:

            keys_to_keep = set(self.mpf_config_spec[section_name].keys())
            empty_entries = set()

            self.log.debug("Converting %s: section", section_name)

            if self.fc[section_name]:

                for name, settings in self.fc[section_name].items():
                    self.log.debug("Converting %s:%s:", section_name, name)
                    if isinstance(settings, dict):
                        keys = set(settings.keys())
                        keys_to_remove = keys - keys_to_keep

                        for key in keys_to_remove:
                            YamlInterface.del_key_with_comments(settings, key,
                                                                self.log)

                    if not settings:
                        self.log.debug("%s:%s: is now empty. Will remove it.",
                                       section_name, name)
                        empty_entries.add(name)

                for name in empty_entries:
                    YamlInterface.del_key_with_comments(self.fc[section_name],
                                                        name, self.log)

            if len(self.fc[section_name]) == 0:
                self.log.debug("%s: is now empty. Will remove it.",
                               section_name)
                YamlInterface.del_key_with_comments(self.fc, section_name,
                                                    self.log)

    def _migrate_elements(self, elements, display=None):
        # takes a list of elements, returns a list of widgets
        if isinstance(elements, dict):
            elements = [elements]

        non_widgets = list()

        for i, element in enumerate(elements):
            elements[i] = self._element_to_widget(element, display)
            if not elements[i]:
                non_widgets.append(elements[i])

        for nw in non_widgets:
            elements.remove(nw)
            # todo do something with these?

        return elements

    def _element_to_widget(self, element, display):
        # takes an element dict, returns a widget dict

        # Figure out which display we're working with so we can get the
        # size to update the positions later. This could be target or
        # display, since this meth is called from a few different places

        if 'target' in element:
            display = element['target']
        elif 'display' in element:
            display = element['display']

        if not display:
            display = V4Migrator.default_display

        if display:
            width, height = V4Migrator.displays[display]
        elif V4Migrator.WIDTH and V4Migrator.HEIGHT:
            width = V4Migrator.WIDTH
            height = V4Migrator.HEIGHT
        else:
            raise ValueError("Unable to auto-detect display with and height. "
                             "Run the migrator again with the -h and -w "
                             "options to manually specific width and height")

        try:
            element_type = element['type'].lower()

        except KeyError:
            return False

        type_map = dict(virtualdmd='dmd',
                        text='text',
                        shape='shape',
                        animation='animation',
                        image='image',
                        movie='video',
                        character_picker='character_picker',
                        entered_chars='entered_chars')

        # Migrate the element type
        element['type'] = type_map[element_type]

        self.log.debug('Converting "%s" display_element to "%s" widget',
                       element_type, element['type'])

        # Migrate layer
        YamlInterface.rename_key('layer', 'z', element, self.log)
        YamlInterface.rename_key('h_pos', 'anchor_x', element, self.log)
        YamlInterface.rename_key('v_pos', 'anchor_y', element, self.log)
        YamlInterface.rename_key('font', 'style', element, self.log)

        if element_type == 'text':
            YamlInterface.rename_key('size', 'font_size', element, self.log)

        y_name = 'middle'
        if 'anchor_y' in element:
            if element['anchor_y'] == 'bottom':
                y_anchor = 0
                y_name = 'bottom'
            elif element['anchor_y'] == 'top':
                y_anchor = height
                y_name = 'top'
            else:
                y_anchor = int(height / 2)
        else:  # middle
            y_anchor = int(height / 2)

        if 'y' in element:
            self.log.debug("Changing y:%s to y:%s (Based on anchor_y:%s and "
                           "%s height:%s)", element['y'],
                           y_anchor - element['y'], y_name, display, height)
            element['y'] = y_anchor - element['y']

        try:
            if element['anchor_x'] == 'right':
                self.log.debug("Changing x:%s to x:%s (Based on anchor_x:"
                               "right and %s width:%s)", element['x'],
                               width + element['x'], display, width)
                element['x'] = width + element['x']
        except KeyError:
            pass

        if element_type == 'animation':
            element = self._migrate_animation(element)
        elif element_type == 'shape':
            element = self._migrate_shape(element)

        if 'decorators' in element:
            element = self._migrate_decorators(element)

        if 'color' in element:
            element['color'] = self._get_color(element['color'])

        return element

    def _get_color(self, color):
        color_tuple = RGBColor.hex_to_rgb(color)

        for color_name, val in named_rgb_colors.items():
            if color_tuple == val:
                self.log.debug("Converting hex color '%s' to named color "
                               "'%s'", color, color_name)
                return color_name

        return color

    def _migrate_shape(self, element):
        if element['shape'] == 'box':
            self.log.debug("Converting 'box' display_element to 'rectangle' "
                           "widget")
            element['type'] = 'rectangle'
            del element['shape']

        elif element['shape'] == 'line':
            self.log.debug("Converting 'line' display_element to 'line' widget")
            element['type'] = 'line'
            del element['shape']

            element['points'] = (element.get('x', 0),
                                 element.get('y', 0),
                                 element.get('x', 0) + element['height'],
                                 element.get('y', 0) + element['width'])
        return element

    def _migrate_animation(self, element):
        self.log.debug("Converting 'animation' display_element to animated "
                       "'image' widget")
        element['type'] = 'image'
        YamlInterface.rename_key('play_now', 'auto_play', element, self.log)
        YamlInterface.rename_key('repeat', 'anim_loops', element, self.log)
        YamlInterface.rename_key('animation', 'image', element, self.log)

        element.pop('drop_frames', None)

        self.log.debug('Converting animated image anim_loops: setting')
        if element['anim_loops']:
            element['anim_loops'] = -1
        else:
            element['anim_loops'] = 0

        return element

    def _migrate_decorators(self, element):
        self.log.debug("Converting display_element blink decorator to widget "
                       "animation")
        decorator = element['decorators']

        element['animations'] = CommentedMap()
        element['animations']['entrance'] = CommentedSeq()

        on_dict = CommentedMap()
        on_dict['property'] = 'opacity'
        on_dict['value'] = 1
        on_dict['duration'] = str(decorator['on_secs']) + 's'

        element['animations']['entrance'].append(on_dict)

        off_dict = CommentedMap()
        off_dict['property'] = 'opacity'
        off_dict['value'] = 0
        off_dict['duration'] = str(decorator['off_secs']) + 's'
        off_dict['repeat'] = True

        element['animations']['entrance'].append(off_dict)

        del element['decorators']

        return element

    def is_show_file(self):
        # Verify we have a show file and that it's an old version
        if 'tocks' in self.fc[0]:
            return True

    def _migrate_show_file(self):
        self.log.debug("Migrating show file: %s", self.file_name)
        # Convert tocks to time

        previous_tocks = 0
        self.log.debug('Converting "tocks:" to "time: and cascading entries "'
                       '"to the next step (since time: is for the current "'
                       '"step versus tocks: being for the previous step"')
        for i, step in enumerate(self.fc):
            previous_tocks = step['tocks']

            if not i:
                step['tocks'] = 0
            else:
                step['tocks'] = '+{}'.format(previous_tocks)

            YamlInterface.rename_key('tocks', 'time', step, self.log)

        self.fc.append(CommentedMap())
        self.fc[-1]['time'] = '+{}'.format(previous_tocks)

        # migrate the components in each step
        self.log.debug("Converting settings for each show step")
        for i, step in enumerate(self.fc):
            if 'display' in step:
                self.log.debug("Show step %s: Converting 'display' section",
                               i+1)
                step['display'] = self._migrate_elements(step['display'])

                for widget in step['display']:
                    if 'transition' in widget:
                        YamlInterface.copy_with_comments(widget, 'transition',
                                                         step, 'transition',
                                                         True, self.log)

        return True

def migrate_file(file_name, file_content):
    return V4Migrator(file_name, file_content).migrate()