##################################################################
#
#   Copyright (C) 2012 Imaginando, Lda & Teenage Engineering AB
#
#   This program is free software; you can redistribute it and/or
#   modify it under the terms of the GNU General Public License
#   as published by the Free Software Foundation; either version 2
#   of the License, or any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   For more information about this license please consult the
#   following webpage: http://www.gnu.org/licenses/gpl-2.0.html
#
##################################################################

# OP-1 Python Scripts V1.0

from __future__ import with_statement

import Live
import time

import consts

# Ableton Live Framework imports

from _Framework.ControlSurface import ControlSurface
from _Framework.TransportComponent import TransportComponent
from _Framework.MixerComponent import MixerComponent
from _Framework.ButtonElement import ButtonElement
from _Framework.EncoderElement import EncoderElement
from _Framework.SessionComponent import SessionComponent
from _Framework.InputControlElement import MIDI_CC_TYPE

# Browser, Arranger, Session, Detail, Detail/Clip, Detail/DeviceChain

# OP-1 imports

from OP1ModeSelectorComponent import OP1ModeSelectorComponent

QUANT_ORDER = [
    Live.Song.Quantization.q_no_q,
    Live.Song.Quantization.q_8_bars,
    Live.Song.Quantization.q_4_bars,
    Live.Song.Quantization.q_2_bars,
    Live.Song.Quantization.q_bar,
    Live.Song.Quantization.q_half,
    Live.Song.Quantization.q_half_triplet,
    Live.Song.Quantization.q_quarter,
    Live.Song.Quantization.q_quarter_triplet,
    Live.Song.Quantization.q_eight,
    Live.Song.Quantization.q_eight_triplet,
    Live.Song.Quantization.q_sixtenth,
    Live.Song.Quantization.q_sixtenth_triplet,
    Live.Song.Quantization.q_thirtytwoth
]


# to properly display strings on op1 display we need to do some character substitution
REPL_CHARS = " " * 32
REPL_CHARS += """ !\"# %    *+,-./0123456789:;<=> @abcdefghijklmnopqrstuvwxyz    _ abcdefghijklmnopqrstuvwxyz -  """   # noqa: E501
REPL_CHARS += " " * 129


def get_q_idx(q):
    idx = QUANT_ORDER.index(q) if q in QUANT_ORDER else None
    return idx


def get_q_enum(idx):
    if idx < 0:
        return QUANT_ORDER[0]
    if idx > len(QUANT_ORDER) - 1:
        return QUANT_ORDER[-1]
    return QUANT_ORDER[idx]


def to_op1_printable(txt):
    """convert a string into OP1 printable character.
    This will change non-printable chars, that would
    be otherwise displayed as '?', into spaces."""
    tr = str(txt).translate(REPL_CHARS)  # replace non-printable chars with spaces
    tr = ' '.join(tr.split())            # replace multiple white space chars with a single space
    return tr[:20]                       # there is 20 character display limit for the bottom line


class OP1(ControlSurface):
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        with self.component_guard():
            self.c_instance = c_instance

            self.retries_count = 0
            self.device_connected = False

            self.clip_color_callbacks = {}
            self.slot_callbacks = {}

            self.text_start_sequence = (0xf0, 0x00, 0x20, 0x76, 0x00, 0x03)
            self.text_end_sequence = (0xf7,)
            self.enable_sequence = (0xf0, 0x00, 0x20, 0x76, 0x00, 0x01, 0x02, 0xf7)
            self.disable_sequence = (0xf0, 0x00, 0x20, 0x76, 0x00, 0x01, 0x00, 0xf7)

            self.id_sequence = (0xf0, 0x7e, 0x7f, 0x06, 0x01, 0xf7)

            self.text_color_start_sequence = (0xf0, 0x0, 0x20, 0x76, 0x00, 0x04)

#           self.log('INITIALIZING')

            self.app = Live.Application.get_application()

            # maj = self.app.get_major_version()
            # min = self.app.get_minor_version()
            # bug = self.app.get_bugfix_version()

            # self.show_message(str(maj) + "." + str(min) + "." + str(bug))

            self.show_message("Version: " + consts.VERSION)

            # reseting text
            self.write_text(' ')

            # reset display clips
            self.reset_display_clips()

            # getting browser visible state
            self.session_browser_visible = self.app.view.is_view_visible("Browser")

            # getting browser visible state
            self.arrange_browser_visible = self.app.view.is_view_visible("Browser")

            # getting detail view visible state
            self.detail_visible = self.app.view.is_view_visible("Detail")

            # getting back to arranger state
            self.back_to_arranger_state = self.song().back_to_arranger

            # initializing channel strip to null
            self._channel_strip = None

            # initializing mixer component
            self._mixer = MixerComponent(consts.NUM_TRACKS, 2)

            # initializing session component
            self._session = SessionComponent(consts.NUM_TRACKS, consts.NUM_ROWS)
            self._session.add_offset_listener(self.session_offset_changed)
            self.set_highlighting_session_component(self._session)
            self._suppress_session_highlight = False

            # initializing transport component
            self._transport = TransportComponent()

            # configuring operation mode selector buttons
            self._operation_mode_buttons = \
                ButtonElement(True, MIDI_CC_TYPE, consts.CHANNEL, consts.OP1_MODE_1_BUTTON), \
                ButtonElement(True, MIDI_CC_TYPE, consts.CHANNEL, consts.OP1_MODE_2_BUTTON), \
                ButtonElement(True, MIDI_CC_TYPE, consts.CHANNEL, consts.OP1_MODE_3_BUTTON), \
                ButtonElement(True, MIDI_CC_TYPE, consts.CHANNEL, consts.OP1_MODE_4_BUTTON),

            # initializing operation mode selector
            self._operation_mode_selector = OP1ModeSelectorComponent(self, self._transport, self._mixer, self._session)  # noqa: E501

            # setting operation mode selector buttons
            self._operation_mode_selector.set_mode_buttons(self._operation_mode_buttons)

            # adding value listener for operation mode index
            self._operation_mode_selector.add_mode_index_listener(self.mode_index_changed)

            # setting global transport assignments
            self._transport.set_stop_button(ButtonElement(True, MIDI_CC_TYPE,
                                                          consts.CHANNEL,
                                                          consts.OP1_STOP_BUTTON))
            self._transport.set_metronome_button(ButtonElement(True,
                                                               MIDI_CC_TYPE,
                                                               consts.CHANNEL,
                                                               consts.OP1_METRONOME_BUTTON))
            self._transport.set_tap_tempo_button(ButtonElement(True,
                                                               MIDI_CC_TYPE,
                                                               consts.CHANNEL,
                                                               consts.OP1_HELP_BUTTON))
            self._transport.set_loop_button(ButtonElement(True, MIDI_CC_TYPE,
                                                          consts.CHANNEL,
                                                          consts.OP1_SS3_BUTTON))
            self._transport.set_overdub_button(ButtonElement(True,
                                                             MIDI_CC_TYPE,
                                                             consts.CHANNEL,
                                                             consts.OP1_SS4_BUTTON))
            self._play_button = ButtonElement(True, MIDI_CC_TYPE,
                                              consts.CHANNEL, consts.OP1_PLAY_BUTTON)
            self._rec_button = ButtonElement(True, MIDI_CC_TYPE,
                                             consts.CHANNEL, consts.OP1_REC_BUTTON)
#                        self._transport.set_play_button(self._play_button)
            self.shift_pressed = False
            self._play_button.add_value_listener(self.play_button_callback)
            self._rec_button.add_value_listener(self.record_button_callback)

# setting global session assignments
            self._ss6_button = ButtonElement(True, MIDI_CC_TYPE,
                                             consts.CHANNEL, consts.OP1_SS6_BUTTON)
            self._micro_button = ButtonElement(True, MIDI_CC_TYPE,
                                               consts.CHANNEL, consts.OP1_MICRO)
            self._com_button = ButtonElement(True, MIDI_CC_TYPE, consts.CHANNEL, consts.OP1_COM)

            # encoder for transport control - leave it empty for now
            self._encoder_1 = EncoderElement(MIDI_CC_TYPE, consts.CHANNEL,
                                             consts.OP1_ENCODER_1,
                                             Live.MidiMap.MapMode.relative_two_compliment)
            self._encoder_2 = EncoderElement(MIDI_CC_TYPE, consts.CHANNEL,
                                             consts.OP1_ENCODER_2,
                                             Live.MidiMap.MapMode.relative_two_compliment)
            self._encoder_3 = EncoderElement(MIDI_CC_TYPE, consts.CHANNEL,
                                             consts.OP1_ENCODER_3,
                                             Live.MidiMap.MapMode.relative_two_compliment)
            self._encoder_4 = EncoderElement(MIDI_CC_TYPE, consts.CHANNEL,
                                             consts.OP1_ENCODER_4,
                                             Live.MidiMap.MapMode.relative_two_compliment)
# setting misc listeners

            self._encoder_1_push = ButtonElement(True, MIDI_CC_TYPE,
                                                 consts.CHANNEL, consts.OP1_ENCODER_1_PUSH)
            self._encoder_2_push = ButtonElement(True, MIDI_CC_TYPE,
                                                 consts.CHANNEL, consts.OP1_ENCODER_2_PUSH)
            self._encoder_3_push = ButtonElement(True, MIDI_CC_TYPE,
                                                 consts.CHANNEL, consts.OP1_ENCODER_3_PUSH)
            self._encoder_4_push = ButtonElement(True, MIDI_CC_TYPE,
                                                 consts.CHANNEL, consts.OP1_ENCODER_4_PUSH)

            self._encoder_3_push.add_value_listener(self.e3_push_callback)
            self._e3_pressed = False
            self._encoder_4_push.add_value_listener(self.e4_push_callback)
            self._e4_pressed = False

            self.mainview_toggle_button = ButtonElement(False, MIDI_CC_TYPE,
                                                        consts.CHANNEL,
                                                        consts.OP1_ARROW_DOWN_BUTTON)
            self.mainview_toggle_button.add_value_listener(self.mainview_toggle_button_callback)

            self.detailview_toggle_button = ButtonElement(False, MIDI_CC_TYPE,
                                                          consts.CHANNEL,
                                                          consts.OP1_SCISSOR_BUTTON)
            self.detailview_toggle_button.add_value_listener(self.detailview_toggle_button_callback)  # noqa: E501

            self.clear_track_button = ButtonElement(True, MIDI_CC_TYPE,
                                                    consts.CHANNEL, consts.OP1_SS8_BUTTON)
            self.clear_track_button.add_value_listener(self.clear_track_button_callback)

            self.back_to_arranger_button = ButtonElement(True, MIDI_CC_TYPE,
                                                         consts.CHANNEL, consts.OP1_SEQ_BUTTON)
            self.back_to_arranger_button.add_value_listener(self.back_to_arranger_button_callback)

            # adding value listener for selected track change
            self.song().view.add_selected_track_listener(self.selected_track_changed)

            # adding value listener for selected scene change
            self.song().view.add_selected_scene_listener(self.selected_scene_changed)

            # setting assignments for currently selected track
            self.selected_track_changed()

            # setting assignments for currently selected scene
            self.selected_scene_changed()

    def handle_sysex(self, midi_bytes):
        if ((midi_bytes[6] == 32) and (midi_bytes[7] == 118)):
            self.device_connected = True
            self.log("OP-1 CONNECTED. SENDING ABLETON LIVE MODE INIT SEQUENCE")
            self._send_midi(self.enable_sequence)

    def add_clip_slot_listeners(self):
        # self.log('ADDING CLIP SLOT LISTENERS')

        # creating an empty list for all clip slots
        clip_slots = []

        # getting a reference to all tracks
        tracks = self.song().tracks

        # appending all tracks clip slots to clip_slots
        for track in tracks:
            clip_slots.append(track.clip_slots)

        # iterating over all clip slots
        for t in range(len(clip_slots)):
            for c in range(len(clip_slots[t])):
                clip_slot = clip_slots[t][c]

                # adding has clip listener to clip slot
                self.add_slot_listener(clip_slot)

                # if clip slot has clip
                if clip_slot.has_clip:
                    # adding clip listeners
                    self.add_clip_listener(clip_slot.clip)

    def rem_clip_slot_listeners(self):
        # self.log('REMOVING CLIP SLOT LISTENERS')

        # iterate over all clip color change callbacks
        for c in self.clip_color_callbacks:
            # if clip still exists
            if c is not None:
                # and it has a has clip listener
                if c.color_has_listener(self.clip_color_callbacks[c]) == 1:
                    # remove it
                    c.remove_color_listener(self.clip_color_callbacks[c])

        # iterate over all clip slot callbacks
        for cs in self.slot_callbacks:
            # if clip slot still exists
            if cs is not None:
                # and it has a has clip listener
                if cs.has_clip_has_listener(self.slot_callbacks[cs]) == 1:
                    # remove it
                    cs.remove_has_clip_listener(self.slot_callbacks[cs])

    def add_slot_listener(self, cs):
        # setting has clip listener
        callback = lambda: self.has_clip_listener(cs)

        # if we don't have a clip slot has clip listener for this clip slot yet
        if not(cs in self.slot_callbacks):
            # adding has clip callback to clip slot
            cs.add_has_clip_listener(callback)

            # saving callback for future release
            self.slot_callbacks[cs] = callback

    def add_clip_listener(self, clip):
        # setting callback for clip color change
        color_callback = lambda: self.update_display_clips()

        # if we don't have a clip color change callback for this clip yet
        if not(clip in self.clip_color_callbacks):
            # adding clip color change callback
            clip.add_color_listener(color_callback)

            # saving callback for future release
            self.clip_color_callbacks[clip] = color_callback

    def has_clip_listener(self, cs):
        # clip slot has clip listener callback
        if cs.has_clip:
            # add clip listener
            self.add_clip_listener(cs.clip)
        else:
            # update display if clip slot was removed
            self.update_display_clips()

    def session_offset_changed(self):
        # if session component offset changes, update display
        self.update_display_clips()

    def selected_scene_changed(self):
        # if on clip mode update display
        if (self._operation_mode_selector.mode_index == consts.OP1_MODE_CLIP):
            self.update_display_clip_mode()

    def e3_push_callback(self, value):
        self._e3_pressed = True if value == 127 else False

    def e4_push_callback(self, value):
        self._e4_pressed = True if value == 127 else False

    def e1_transport_scrub(self, value):
        if value == 4:
            self.song().scrub_by(1)
        else:
            self.song().scrub_by(-1)

    def e2_transport_scrub(self, value):
        if value == 4:
            x = 1
        else:
            x = -1
        idx = get_q_idx(self.song().clip_trigger_quantization)
        self.song().clip_trigger_quantization = get_q_enum(idx + x)

    def e_transport_scroll(self, value, b):
        """This will move arrangement cursor left/right, with a selection
        if pressed. Up/Down modifiers do not do anything in Live 9.2 """
        if value == 4:
            x = Live.Application.Application.View.NavDirection.right
        else:
            x = Live.Application.Application.View.NavDirection.left
        self.app.view.scroll_view(x, "Arranger", b)

    def e3_transport_scroll(self, value):
        self.e_transport_scroll(value, self._e3_pressed)

    def e4_transport_zoom(self, value):
        """Zoom arrangement view 'into' the track or make track widget bigger/smaller.
        The boolean parameter to zoom_view() does funky things
        and is not really useful to set it to True."""
        if value == 4:
            x = Live.Application.Application.View.NavDirection.down \
                if self._e4_pressed \
                else Live.Application.Application.View.NavDirection.right
        else:
            x = Live.Application.Application.View.NavDirection.up \
                if self._e4_pressed \
                else Live.Application.Application.View.NavDirection.left
        self.app.view.zoom_view(x, "Arranger", False)

    def play_button_callback(self, value):
        if value == 127:
            if self.shift_pressed is True:
                self.song().play_selection()
            else:
                self.song().start_playing()

    def record_button_callback(self, value):
        if value == 127:
            self.song().record_mode = not self.song().record_mode

    def mode_index_changed(self):

        # update display to current mode info
        if (self._operation_mode_selector.mode_index == consts.OP1_MODE_PERFORM):
            self.update_display_perform_mode()
        elif (self._operation_mode_selector.mode_index == consts.OP1_MODE_CLIP):
            self.update_display_clip_mode()
        elif (self._operation_mode_selector.mode_index == consts.OP1_MODE_TRANSPORT):
            self.update_display_transport_mode()
        elif (self._operation_mode_selector.mode_index == consts.OP1_MODE_MIXER):
            self.update_display_mixer_mode()

    def mic_button_sel_up(self, value):
        if value == 127:
            x = Live.Application.Application.View.NavDirection.up
            self.app.view.scroll_view(x, "Arranger", False)

    def com_button_sel_down(self, value):
        if value == 127:
            x = Live.Application.Application.View.NavDirection.down
            self.app.view.scroll_view(x, "Arranger", False)

    def clear_track_button_callback(self, value):
        # if clear track button was called, reset track
        if (value == 127):
            for i in range(len(self.song().tracks)):
                track = self.song().tracks[i]
                if track.can_be_armed is True:
                    self.song().tracks[i].arm = 0
                self.song().tracks[i].solo = 0
                self.song().tracks[i].mute = 0

            for i in range(len(self.song().return_tracks)):
                self.song().tracks[i].solo = 0
                self.song().tracks[i].mute = 0

    def clear_return_track_assignment(self, strip):
        # clear return track assingments
        strip.set_volume_control(None)
        strip.set_pan_control(None)
        strip.set_mute_button(None)
        strip.set_solo_button(None)

    def clear_track_assignment(self, strip):
        # clear track assignments
        strip.set_volume_control(None)
        strip.set_pan_control(None)
        strip.set_mute_button(None)
        strip.set_solo_button(None)
        strip.set_arm_button(None)

    def clear_tracks_assigments(self):
        # for all normal tracks, clear assignments
        self.clear_track_assignment(self._mixer.selected_strip())
        self.clear_return_track_assignment(self._mixer.selected_strip())
        self._mixer.selected_strip().set_send_controls(tuple((None, None)))
        for i in range(consts.NUM_TRACKS):
            strip = self._mixer.channel_strip(i)
            if (strip is not None):
                self.clear_track_assignment(strip)

        # for all return tracks, clear assignments
        for i in range(2):
            return_strip = self._mixer.return_strip(i)
            if (return_strip is not None):
                self.clear_return_track_assignment(return_strip)

    def selected_track_changed(self):
        # if on mixer mode update display
        if (self._operation_mode_selector.mode_index == consts.OP1_MODE_MIXER):
            self.update_display_mixer_mode()

        # clear track assignments
        self.clear_tracks_assigments()

        # getting selected strip
        self._channel_strip = self._mixer.selected_strip()

        # setting solo button
        self._channel_strip.set_solo_button(self._ss6_button)

        # if track can be armed, set arm button
        if (self._channel_strip._track.can_be_armed):
            b = ButtonElement(True, MIDI_CC_TYPE, consts.CHANNEL, consts.OP1_SS7_BUTTON)
            self._channel_strip.set_arm_button(b)

        # if track is no master, set mute button
        if (self._channel_strip._track != self.song().master_track):
            b = ButtonElement(True, MIDI_CC_TYPE, consts.CHANNEL, consts.OP1_SS5_BUTTON)
            self._channel_strip.set_mute_button(b)

        # if transport mode, we don't want to map encoders
        if (self._operation_mode_selector.mode_index == consts.OP1_MODE_TRANSPORT):
            return

        # perform track assignments
        self._channel_strip.set_volume_control(self._encoder_1)
        self._channel_strip.set_pan_control(self._encoder_2)

        # setting a tuple of encoders to control sends
        send_controls = self._encoder_3, self._encoder_4,

        # setting send encoders
        self._channel_strip.set_send_controls(tuple(send_controls))

    def back_to_arranger_button_callback(self, value):
        if (value == 127):
            if self.shift_pressed is False:
                self.song().back_to_arranger = False
            else:
                self.song().view.follow_song = not self.song().view.follow_song

    def mainview_toggle_button_callback(self, value):
        if self.shift_pressed is True:
            if value == 127:
                self.song().undo()
        else:
            if (value == 127):
                if (self.app.view.is_view_visible("Session")):
                    self.app.view.show_view("Arranger")
                    self.arrange_browser_visible = self.app.view.is_view_visible("Browser")
                else:
                    self.app.view.show_view("Session")
                    self.session_browser_visible = self.app.view.is_view_visible("Browser")

    def detailview_toggle_button_callback(self, value):
        if self.shift_pressed is True:
            if value == 127:
                self.song().redo()
        else:
            if (value == 127):
                if (self.detail_visible is True):
                    self.detail_visible = False
                    self.app.view.hide_view("Detail")
                else:
                    self.detail_visible = True
                    self.app.view.show_view("Detail")

    def write_text(self, msg):
        text_list = []
        sequence = ()

        text_list.append(len(msg.strip()))

        for i in msg.strip():
            text_list.append(ord(i))

        sequence = self.text_start_sequence + tuple(text_list) + self.text_end_sequence
        self._send_midi(sequence)

    def suggest_input_port(self):
        return "OP-1 Midi Device"

    def suggest_output_port(self):
        return "OP-1 Midi Device"

    def update_display_perform_mode(self):
        self.write_text("perform\rmode")

    def reset_display_clips(self):
        count = 0
        colors = []
        length = []
        sequence = ()

        for i in range(consts.NUM_TRACKS):
            count += 1

            colors.append(0x00)
            colors.append(0x00)
            colors.append(0x00)

        length.append(count)
        sequence = self.text_color_start_sequence + tuple(length) + \
            tuple(colors) + self.text_end_sequence
        self._send_midi(sequence)

    def update_display_clips(self):
        # self.log("UPDATING DISPLAY CLIPS")
        count = 0
        colors = []
        length = []
        sequence = ()

        tracks_len = len(self.song().tracks) - self._session._track_offset

        if (tracks_len > consts.NUM_TRACKS):
            tracks_len = consts.NUM_TRACKS

        for i in range(tracks_len):
            count += 1
            clip_slot = self._session.scene(0).clip_slot(i)

            color = (0x00, 0x00, 0x00)
            if (clip_slot is not None) and (clip_slot._clip_slot is not None):
                if clip_slot.has_clip():
                    clip_color = clip_slot._clip_slot.clip.color
                    color = (((clip_color >> 16) & 0x000000ff) >> 1,
                             ((clip_color >> 8) & 0x000000ff) >> 1,
                             (clip_color & 0x000000ff) >> 1)

            colors += color

        length.append(count)
        sequence = self.text_color_start_sequence + tuple(length) + \
            tuple(colors) + self.text_end_sequence
        self._send_midi(sequence)

    def update_display_clip_mode(self):
        txt = self.song().view.selected_scene.name.lower()
        txt = to_op1_printable(txt)
        self.write_text("sel. scene\r" + txt)

    def get_quant_str(self, q):
        qmap = {
            Live.Song.Quantization.q_2_bars: "2b",
            Live.Song.Quantization.q_4_bars: "4b",
            Live.Song.Quantization.q_8_bars: "8b",
            Live.Song.Quantization.q_bar: "1b",
            Live.Song.Quantization.q_half: "/2",
            Live.Song.Quantization.q_half_triplet: "/2t",
            Live.Song.Quantization.q_quarter: "/4",
            Live.Song.Quantization.q_quarter_triplet: "/4t",
            Live.Song.Quantization.q_eight: "/8",
            Live.Song.Quantization.q_eight_triplet: "/8t",
            Live.Song.Quantization.q_sixtenth: "/16",
            Live.Song.Quantization.q_sixtenth_triplet: "/16t",
            Live.Song.Quantization.q_thirtytwoth: "/32",
            Live.Song.Quantization.q_no_q: "non"
        }
        return qmap[q] if q in qmap else ":("

    def update_display_transport_mode(self):
        song_time = str(self.song().get_current_beats_song_time())
        playing = '>' if self.song().is_playing else ''
        record = '*' if self.song().record_mode else ''
        txt = playing + record
        txt += " " + self.get_quant_str(self.song().clip_trigger_quantization)
        txt += " " + str("%.2f" % round(self.song().tempo, 2))
        txt += "\r" + song_time[:len(song_time) - 4]
        self.write_text(txt)

    def update_display_mixer_mode(self):
        txt = self.song().view.selected_track.name.lower()
        txt = to_op1_printable(txt)
        self.write_text("sel. track\r" + txt)

    def update_display(self):
        if not(self.device_connected):
            if (self.retries_count < 5):
                self.log("TRYING OP-1 CONNECTION")
                self.retries_count += 1
                self._send_midi(self.id_sequence)
                time.sleep(1)

        # if in transport mode, update display with song position
        if (self._operation_mode_selector.mode_index == consts.OP1_MODE_TRANSPORT):
            self.update_display_transport_mode()

        # checking if app current view is session
        if (self.app.view.is_view_visible("Session")):
            # checking if session browser state is diferent from the internal
            if (self.session_browser_visible != self.app.view.is_view_visible("Browser")):
                self.session_browser_visible = self.app.view.is_view_visible("Browser")

        # checking if app current view is arrange
        if (self.app.view.is_view_visible("Arranger")):
            # checking if arrange browser state is diferent from the internal
            if (self.arrange_browser_visible != self.app.view.is_view_visible("Browser")):
                self.arrange_browser_visible = self.app.view.is_view_visible("Browser")

        # checking if app current view is detail
        if (self.app.view.is_view_visible("Detail")):
            # checking if detail state is diferent from the internal
            if (self.detail_visible != self.app.view.is_view_visible("Detail")):
                self.detail_visible = self.app.view.is_view_visible("Detail")

    def refresh_state(self):
        self.log("REFRESH STATE")
        self.retries_count = 0
        self.device_connected = False

    def build_midi_map(self, midi_map_handle):
        self._current_midi_map = midi_map_handle
        ControlSurface.build_midi_map(self, midi_map_handle)

        # remove clip listeners
        self.rem_clip_slot_listeners()

        # add clip listeners
        self.add_clip_slot_listeners()

        # update display
        self.update_display_clips()

    def log(self, msg):
        self.c_instance.log_message("[TE OP-1] " + msg)

    def disconnect(self):
        # removing clip slots listeners
        self.rem_clip_slot_listeners()

        # removing value listener for track changed
        self.song().view.remove_selected_track_listener(self.selected_track_changed)

        # removing value listener for scene changed
        self.song().view.remove_selected_scene_listener(self.selected_scene_changed)

        # removing value listener for operation mode index
        self._operation_mode_selector.remove_mode_index_listener(self.mode_index_changed)

        # removing global transport assignments
        self._transport.set_punch_buttons(None, None)
        self._transport.set_loop_button(None)
        self._transport.set_overdub_button(None)
        self._transport.set_record_button(None)
        self._transport.set_play_button(None)
        self._transport.set_stop_button(None)
        self._transport.set_metronome_button(None)
        self._transport.set_tap_tempo_button(None)

        # removing global session assignments
        self._session.set_scene_bank_buttons(None, None)

        # removing misc listeners
        self.browser_toggle_button.remove_value_listener(self.browser_toggle_button_callback)
        self.mainview_toggle_button.remove_value_listener(self.mainview_toggle_button_callback)
        self.detailview_toggle_button.remove_value_listener(self.detailview_toggle_button_callback)
        self.clear_track_button.remove_value_listener(self.clear_track_button_callback)
        self.back_to_arranger_button.remove_value_listener(self.back_to_arranger_button_callback)

        # sending special ableton mode disable sequence
        self._send_midi(self.disable_sequence)

        # disconnecting control surface
        ControlSurface.disconnect(self)

        self.log("DISCONNECTED")
