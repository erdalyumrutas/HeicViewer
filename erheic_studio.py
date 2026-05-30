import customtkinter as ctk
from PIL import ImageTk, Image, ImageEnhance, ImageOps, ImageGrab, ImageFilter, ImageDraw, ImageFont, ImageColor
from pillow_heif import register_heif_opener
from tkinter import filedialog, messagebox, Menu, simpledialog, colorchooser
import os
import sys
import tempfile
import io
import time
from pathlib import Path
from glob import glob

# HEIC desteğini kaydet
register_heif_opener()

# Tema ayarları
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class UniversalPhotoStudio(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Temel değişkenler
        self.zoom_level = 1.0
        self.raw_image = None
        self.processed_image = None
        self.current_path = None
        self.source_name = None
        self.folder_images = []
        self.rotation_angle = 0
        self.supported_exts = (".heic", ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".ico")
        self.undo_stack = []
        self.redo_stack = []
        self.history_limit = 20
        self._suspend_history = False
        self.pending_slider_snapshot = None

        # Seçim değişkenleri
        self.selection_rect = None
        self.selection_coords = None
        self.start_x = None
        self.start_y = None
        self.tk_img = None
        self.display_image_bbox = None
        self.rendered_image_size = (0, 0)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.min_selection_size = 8
        self.heal_brush_mode = False
        self.heal_brush_size = 28
        self.heal_mask_points = []
        self.heal_overlay_ids = []
        self.pending_insert = None
        self.annotation_snapshots = []
        self.pending_insert_canvas_id = None
        self.pending_insert_drag_offset = None
        self.last_text_color = "#FFFFFF"
        self.text_layers = []
        self.selected_layer_index = -1

        self.title("ErheiC Studio Pro - Ultimate Edition @erdal.27.5.26")

        # UI layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sol panel
        self.sidebar = ctk.CTkFrame(self, width=320, corner_radius=0, fg_color="#1A1A1A")
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(
            self.sidebar,
            text="ERHEIC ULTIMATE",
            font=("Tahoma", 20, "bold"),
            text_color="#3B8ED0",
        ).pack(pady=(20, 5))

        self.info_container = ctk.CTkScrollableFrame(
            self.sidebar,
            label_text="BİLGİ & DÜZENLEME",
            fg_color="#252525",
        )
        self.info_container.pack(fill="both", expand=True, padx=15, pady=10)

        self.setup_edit_controls()
        self.setup_menu_bar()

        # Sağ panel
        self.main_view = ctk.CTkFrame(self, fg_color="transparent")
        self.main_view.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")

        self.display_frame = ctk.CTkFrame(self.main_view, fg_color="#141414", corner_radius=12)
        self.display_frame.pack(expand=True, fill="both")
        self.display_frame.grid_rowconfigure(0, weight=1)
        self.display_frame.grid_columnconfigure(0, weight=1)

        self.canvas = ctk.CTkCanvas(self.display_frame, bg="#141414", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scrollbar = ctk.CTkScrollbar(self.display_frame, orientation="vertical", command=self.on_vertical_scroll)
        self.v_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=8)
        self.v_scrollbar.set(0.0, 1.0)
        self.v_scrollbar.grid_remove()
        self.h_scrollbar = ctk.CTkScrollbar(self.display_frame, orientation="horizontal", command=self.on_horizontal_scroll)
        self.h_scrollbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        self.h_scrollbar.set(0.0, 1.0)
        self.h_scrollbar.grid_remove()

        # Olay bağları
        self.canvas.bind("<ButtonPress-1>", self.on_start_selection)
        self.canvas.bind("<B1-Motion>", self.on_drag_selection)
        self.canvas.bind("<ButtonRelease-1>", self.on_end_selection)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.bind_all("<Left>", lambda e: self.navigate(-1))
        self.bind_all("<Right>", lambda e: self.navigate(1))
        self.bind_shortcuts()

        # Pencere boyutu değiştiğinde resmi yeniden ölçekle
        self.canvas.bind("<Configure>", lambda e: self.update_view())

        self.set_image_actions_enabled(False)
        self.after(0, self.ensure_maximized)
        self.after(500, self.check_args)

    def get_active_image(self):
        return self.processed_image if self.processed_image else self.raw_image

    def ensure_maximized(self):
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                self.update_idletasks()
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    def setup_edit_controls(self):
        self.sliders = {}
        self.zoom_slider = None
        self.zoom_value_label = None
        self.reset_filters_button = None
        self.preset_menu = None
        self.preset_var = ctk.StringVar(value="Preset: Yok")
        self.skin_preset_menu = None
        self.skin_preset_var = ctk.StringVar(value="Cilt Rötuş: Yok")
        self.gpu_accel_var = ctk.BooleanVar(value=True)
        self.slider_defaults = {}
        controls = [
            ("Parlaklık", 0.5, 1.5, 1.0),
            ("Kontrast", 0.5, 1.5, 1.0),
            ("Keskinlik", 0.0, 2.0, 1.0),
            ("Doygunluk", 0.0, 2.0, 1.0),
            ("Exposure", -2.0, 2.0, 0.0),
            ("Temperature", -100.0, 100.0, 0.0),
            ("Tint", -100.0, 100.0, 0.0),
            ("Vibrance", -100.0, 100.0, 0.0),
            ("Clarity", -100.0, 100.0, 0.0),
            ("Dehaze", -100.0, 100.0, 0.0),
        ]

        for name, start, end, default_value in controls:
            self.slider_defaults[name] = default_value
            ctk.CTkLabel(self.info_container, text=name, font=("Arial", 10)).pack(pady=(5, 0))
            slider = ctk.CTkSlider(self.info_container, from_=start, to=end, command=self.apply_filters)
            slider.set(default_value)
            slider.pack(padx=10, pady=5)
            slider.bind("<ButtonPress-1>", self.on_slider_press)
            slider.bind("<ButtonRelease-1>", self.on_slider_release)
            self.sliders[name] = slider

        ctk.CTkLabel(self.info_container, text="Preset", font=("Arial", 10)).pack(pady=(8, 0))
        self.preset_menu = ctk.CTkOptionMenu(
            self.info_container,
            values=[
                "Preset: Yok",
                "Portrait",
                "Cinematic",
                "Warm",
                "Cool",
                "BW Matte",
            ],
            variable=self.preset_var,
            command=self.apply_preset,
        )
        self.preset_menu.pack(padx=10, pady=(5, 8), fill="x")

        ctk.CTkLabel(self.info_container, text="Cilt Rötuş", font=("Arial", 10)).pack(pady=(8, 0))
        self.skin_preset_menu = ctk.CTkOptionMenu(
            self.info_container,
            values=["Cilt Rötuş: Yok", "Hafif", "Orta", "Güçlü"],
            variable=self.skin_preset_var,
            command=self.apply_skin_preset,
        )
        self.skin_preset_menu.pack(padx=10, pady=(5, 8), fill="x")

        ctk.CTkLabel(self.info_container, text="Yazı Stili", font=("Arial", 10, "bold")).pack(pady=(10, 0))
        self.text_font_var = ctk.StringVar(value="Arial")
        self.text_font_menu = ctk.CTkOptionMenu(
            self.info_container,
            values=["Arial", "Tahoma", "Segoe UI", "Times New Roman", "Courier New", "Segoe UI Emoji"],
            variable=self.text_font_var,
            command=lambda _v: self.update_selected_layer_style(),
        )
        self.text_font_menu.pack(padx=10, pady=(5, 6), fill="x")

        self.text_bold_var = ctk.BooleanVar(value=False)
        self.text_italic_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self.info_container,
            text="Bold",
            variable=self.text_bold_var,
            onvalue=True,
            offvalue=False,
            command=self.update_selected_layer_style,
        ).pack(padx=10, pady=(2, 2), anchor="w")
        ctk.CTkCheckBox(
            self.info_container,
            text="Italic",
            variable=self.text_italic_var,
            onvalue=True,
            offvalue=False,
            command=self.update_selected_layer_style,
        ).pack(padx=10, pady=(2, 6), anchor="w")

        ctk.CTkLabel(self.info_container, text="Opaklık", font=("Arial", 10)).pack(pady=(0, 0))
        self.text_opacity_slider = ctk.CTkSlider(
            self.info_container,
            from_=0.1,
            to=1.0,
            number_of_steps=90,
            command=lambda _v: self.update_selected_layer_style(),
        )
        self.text_opacity_slider.set(1.0)
        self.text_opacity_slider.pack(padx=10, pady=(4, 6), fill="x")

        ctk.CTkLabel(self.info_container, text="Kenar Kalınlığı", font=("Arial", 10)).pack(pady=(0, 0))
        self.text_stroke_slider = ctk.CTkSlider(
            self.info_container,
            from_=0,
            to=6,
            number_of_steps=6,
            command=lambda _v: self.update_selected_layer_style(),
        )
        self.text_stroke_slider.set(1)
        self.text_stroke_slider.pack(padx=10, pady=(4, 6), fill="x")

        ctk.CTkLabel(self.info_container, text="Katmanlar", font=("Arial", 10, "bold")).pack(pady=(8, 0))
        self.layer_var = ctk.StringVar(value="Katman Yok")
        self.layer_menu = ctk.CTkOptionMenu(
            self.info_container,
            values=["Katman Yok"],
            variable=self.layer_var,
            command=self.on_layer_selected,
        )
        self.layer_menu.pack(padx=10, pady=(5, 6), fill="x")
        layer_btn_row = ctk.CTkFrame(self.info_container, fg_color="transparent")
        layer_btn_row.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(layer_btn_row, text="Yukarı", width=70, command=lambda: self.move_layer(-1)).pack(side="left", padx=2, expand=True)
        ctk.CTkButton(layer_btn_row, text="Aşağı", width=70, command=lambda: self.move_layer(1)).pack(side="left", padx=2, expand=True)
        ctk.CTkButton(layer_btn_row, text="Sil", width=70, command=self.delete_selected_layer).pack(side="left", padx=2, expand=True)

        ctk.CTkLabel(self.info_container, text="Zoom", font=("Arial", 10)).pack(pady=(8, 0))
        self.zoom_slider = ctk.CTkSlider(self.info_container, from_=0.1, to=5.0, command=self.on_zoom_slider)
        self.zoom_slider.set(self.zoom_level)
        self.zoom_slider.pack(padx=10, pady=(5, 2))
        self.zoom_value_label = ctk.CTkLabel(self.info_container, text=f"{int(self.zoom_level * 100)}%", font=("Arial", 10))
        self.zoom_value_label.pack(pady=(0, 8))

        ctk.CTkLabel(self.info_container, text="Leke Fırça Boyutu", font=("Arial", 10)).pack(pady=(8, 0))
        self.heal_brush_slider = ctk.CTkSlider(
            self.info_container,
            from_=6,
            to=120,
            number_of_steps=114,
            command=self.on_heal_brush_size_change,
        )
        self.heal_brush_slider.set(self.heal_brush_size)
        self.heal_brush_slider.pack(padx=10, pady=(5, 2))
        self.heal_brush_value_label = ctk.CTkLabel(self.info_container, text=f"{self.heal_brush_size}px", font=("Arial", 10))
        self.heal_brush_value_label.pack(pady=(0, 8))

        self.gpu_checkbox = ctk.CTkCheckBox(
            self.info_container,
            text="GPU Hızlandırma (CUDA)",
            variable=self.gpu_accel_var,
            onvalue=True,
            offvalue=False,
        )
        self.gpu_checkbox.pack(padx=10, pady=(4, 8), anchor="w")

        self.reset_filters_button = ctk.CTkButton(
            self.info_container,
            text="Filtreleri Sıfırla",
            height=25,
            command=self.reset_filters,
        )
        self.reset_filters_button.pack(pady=10)

        self.meta_label = ctk.CTkLabel(
            self.info_container,
            text="Resim yüklenmedi",
            justify="left",
            wraplength=250,
        )
        self.meta_label.pack(pady=10, padx=5)

        self.status_label = ctk.CTkLabel(
            self.info_container,
            text="Durum: Hazır",
            justify="left",
            wraplength=250,
            text_color="#BDBDBD",
        )
        self.status_label.pack(pady=(0, 10), padx=5)

    def setup_menu_bar(self):
        menu_bar = Menu(self)

        self.file_menu = Menu(menu_bar, tearoff=0)
        self.file_menu.add_command(label="Dosya Aç", accelerator="Ctrl+O", command=self.open_file_dialog)
        self.file_menu.add_command(label="Kaydet", accelerator="Ctrl+S", command=self.save_current_file)
        self.file_menu.add_command(label="Farklı Kaydet", accelerator="Ctrl+Shift+S", command=self.save_as_dialog)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="JPEG Kaydet", command=lambda: self.convert_image("JPEG"))
        self.file_menu.add_command(label="PNG Kaydet", command=lambda: self.convert_image("PNG"))
        self.file_menu.add_command(label="ICO Kaydet", command=lambda: self.convert_image("ICO"))
        self.file_menu.add_command(label="PDF Kaydet", command=lambda: self.convert_image("PDF"))
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Yazdır", command=self.print_image)
        self.file_menu.add_command(label="AI Arka Plan Sil", command=self.remove_background_ai)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Çıkış", command=self.quit)
        menu_bar.add_cascade(label="Dosya", menu=self.file_menu)

        self.edit_menu = Menu(menu_bar, tearoff=0)
        self.edit_menu.add_command(label="Geri Al", accelerator="Ctrl+Z", command=self.undo_action)
        self.edit_menu.add_command(label="Yinele", accelerator="Ctrl+Y", command=self.redo_action)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Kopyala", accelerator="Ctrl+C", command=self.copy_to_clipboard)
        self.edit_menu.add_command(label="Yapıştır", accelerator="Ctrl+V", command=self.paste_from_clipboard)
        self.edit_menu.add_command(label="Seçili Alanı Kopyala", accelerator="Ctrl+Shift+C", command=self.copy_selection)
        self.edit_menu.add_command(label="Seçime Göre Kırp", accelerator="Ctrl+Shift+X", command=self.crop_to_selection)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Yazı Ekle", command=self.start_add_text)
        self.edit_menu.add_command(label="Emoji Ekle", command=self.start_add_emoji)
        self.edit_menu.add_command(label="Yazı/Emoji Uygula", command=self.apply_pending_insert)
        self.edit_menu.add_command(label="Yazı/Emoji İptal", command=self.cancel_pending_insert)
        self.edit_menu.add_command(label="Son Yazı/Emoji Sil", command=self.remove_last_annotation)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Leke Fırça Modu", accelerator="B", command=self.toggle_heal_brush_mode)
        self.edit_menu.add_command(label="Leke Maskesini Uygula", accelerator="Enter", command=self.apply_heal_brush)
        self.edit_menu.add_command(label="Leke Maskesini Temizle", accelerator="Esc", command=self.clear_heal_overlay)
        self.edit_menu.add_command(label="Akıllı Sil (Deneysel)", accelerator="Ctrl+Shift+Delete", command=self.remove_selection_content)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Filtreleri Sıfırla", command=self.reset_filters)
        menu_bar.add_cascade(label="Düzenle", menu=self.edit_menu)

        self.view_menu = Menu(menu_bar, tearoff=0)
        self.view_menu.add_command(label="Sola Döndür", command=lambda: self.rotate_image(-90))
        self.view_menu.add_command(label="Sağa Döndür", command=lambda: self.rotate_image(90))
        self.view_menu.add_command(label="Yatay Aynala", command=self.flip_image)
        self.view_menu.add_separator()
        self.view_menu.add_command(label="Önceki Görsel", accelerator="Sol Ok", command=lambda: self.navigate(-1))
        self.view_menu.add_command(label="Sonraki Görsel", accelerator="Sağ Ok", command=lambda: self.navigate(1))
        menu_bar.add_cascade(label="Görüntüle", menu=self.view_menu)

        self.config(menu=menu_bar)

    def set_image_actions_enabled(self, enabled):
        state = "normal" if enabled else "disabled"

        for slider in self.sliders.values():
            slider.configure(state=state)
        if self.preset_menu is not None:
            self.preset_menu.configure(state=state)
        if self.skin_preset_menu is not None:
            self.skin_preset_menu.configure(state=state)
        if self.zoom_slider is not None:
            self.zoom_slider.configure(state=state)
        if hasattr(self, "heal_brush_slider") and self.heal_brush_slider is not None:
            self.heal_brush_slider.configure(state=state)
        if hasattr(self, "gpu_checkbox") and self.gpu_checkbox is not None:
            self.gpu_checkbox.configure(state=state)
        if self.reset_filters_button is not None:
            self.reset_filters_button.configure(state=state)

        # Dosya menüsü: Kaydet/Farklı Kaydet + format kaydet + yazdır
        for idx in (1, 2, 4, 5, 6, 7, 9, 10):
            self.file_menu.entryconfigure(idx, state=state)

        # Düzenle menüsü: tüm işlem komutları (ayraçlar hariç)
        for idx in (0, 1, 3, 4, 5, 6, 8, 9, 10, 11, 12, 14, 15, 16, 17, 19):
            self.edit_menu.entryconfigure(idx, state=state)

        # Görüntüle menüsü: tüm işlem komutları (ayraç hariç)
        for idx in (0, 1, 2, 4, 5):
            self.view_menu.entryconfigure(idx, state=state)

    def update_status(self, text):
        self.status_label.configure(text=f"Durum: {text}")

    def refresh_layer_menu(self):
        if not hasattr(self, "layer_menu"):
            return
        if not self.text_layers:
            self.layer_menu.configure(values=["Katman Yok"])
            self.layer_var.set("Katman Yok")
            self.selected_layer_index = -1
            return
        labels = []
        for idx, layer in enumerate(self.text_layers):
            kind = "Emoji" if layer.get("type") == "emoji" else "Yazı"
            labels.append(f"{idx + 1}. {kind}: {layer.get('value', '')[:14]}")
        self.layer_menu.configure(values=labels)
        self.selected_layer_index = max(0, min(self.selected_layer_index, len(labels) - 1))
        self.layer_var.set(labels[self.selected_layer_index])

    def on_layer_selected(self, selected_label):
        if not self.text_layers:
            return
        vals = self.layer_menu.cget("values")
        try:
            self.selected_layer_index = list(vals).index(selected_label)
        except Exception:
            return
        layer = self.text_layers[self.selected_layer_index]
        self.text_font_var.set(layer.get("font_family", "Arial"))
        self.text_bold_var.set(bool(layer.get("bold", False)))
        self.text_italic_var.set(bool(layer.get("italic", False)))
        self.text_opacity_slider.set(float(layer.get("opacity", 1.0)))
        self.text_stroke_slider.set(float(layer.get("stroke", 1)))
        self.apply_filters()

    def update_selected_layer_style(self):
        if self.selected_layer_index < 0 or self.selected_layer_index >= len(self.text_layers):
            return
        layer = self.text_layers[self.selected_layer_index]
        layer["font_family"] = self.text_font_var.get()
        layer["bold"] = bool(self.text_bold_var.get())
        layer["italic"] = bool(self.text_italic_var.get())
        layer["opacity"] = float(self.text_opacity_slider.get())
        layer["stroke"] = int(round(float(self.text_stroke_slider.get())))
        self.apply_filters()

    def delete_selected_layer(self):
        if self.selected_layer_index < 0 or self.selected_layer_index >= len(self.text_layers):
            self.update_status("Silinecek katman yok.")
            return
        self.push_undo_state()
        self.text_layers.pop(self.selected_layer_index)
        self.selected_layer_index = min(self.selected_layer_index, len(self.text_layers) - 1)
        self.refresh_layer_menu()
        self.apply_filters()
        self.update_status("Katman silindi.")

    def move_layer(self, direction):
        idx = self.selected_layer_index
        if idx < 0 or idx >= len(self.text_layers):
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.text_layers):
            return
        self.push_undo_state()
        self.text_layers[idx], self.text_layers[new_idx] = self.text_layers[new_idx], self.text_layers[idx]
        self.selected_layer_index = new_idx
        self.refresh_layer_menu()
        self.apply_filters()
        self.update_status("Katman sırası değişti.")

    def _clamp_u8(self, value):
        return max(0, min(255, int(value)))

    def hex_to_rgba(self, color_hex, alpha):
        try:
            r, g, b = ImageColor.getrgb(color_hex)
            return (r, g, b, alpha)
        except Exception:
            return (255, 255, 255, alpha)

    def apply_temperature_tint(self, img, temperature, tint):
        if abs(temperature) < 0.1 and abs(tint) < 0.1:
            return img
        r, g, b = img.split()
        t = temperature / 100.0
        ti = tint / 100.0
        r_factor = 1.0 + (0.18 * t) + (0.08 * ti)
        b_factor = 1.0 - (0.18 * t) + (0.08 * ti)
        g_factor = 1.0 - (0.14 * ti)
        r = r.point(lambda p: self._clamp_u8(p * r_factor))
        g = g.point(lambda p: self._clamp_u8(p * g_factor))
        b = b.point(lambda p: self._clamp_u8(p * b_factor))
        return Image.merge("RGB", (r, g, b))

    def apply_preset(self, preset_name):
        if self.raw_image is None or self._suspend_history:
            return
        self.push_undo_state()
        preset_values = {
            "Preset: Yok": {},
            "Portrait": {"Parlaklık": 1.06, "Kontrast": 1.08, "Doygunluk": 1.06, "Temperature": 8.0, "Clarity": 18.0},
            "Cinematic": {"Kontrast": 1.18, "Doygunluk": 0.88, "Temperature": -10.0, "Tint": 6.0, "Dehaze": 16.0},
            "Warm": {"Temperature": 25.0, "Doygunluk": 1.08, "Exposure": 0.15},
            "Cool": {"Temperature": -25.0, "Tint": -8.0, "Kontrast": 1.05, "Exposure": -0.05},
            "BW Matte": {"Doygunluk": 0.0, "Kontrast": 0.88, "Parlaklık": 1.06, "Dehaze": -18.0},
        }
        values = dict(self.slider_defaults)
        values.update(preset_values.get(preset_name, {}))
        self.set_slider_values(values)
        self.apply_filters()
        self.update_status(f"{preset_name} uygulandı.")

    def apply_skin_preset(self, preset_name):
        if self.raw_image is None or self._suspend_history:
            return
        self.push_undo_state()
        skin_values = {
            "Cilt Rötuş: Yok": {},
            "Hafif": {"Parlaklık": 1.02, "Kontrast": 0.97, "Clarity": -10.0, "Dehaze": -6.0, "Vibrance": -4.0},
            "Orta": {"Parlaklık": 1.04, "Kontrast": 0.94, "Clarity": -18.0, "Dehaze": -10.0, "Vibrance": -8.0},
            "Güçlü": {"Parlaklık": 1.06, "Kontrast": 0.90, "Clarity": -28.0, "Dehaze": -14.0, "Vibrance": -12.0},
        }
        values = dict(self.slider_defaults)
        values.update(skin_values.get(preset_name, {}))
        self.set_slider_values(values)
        self.apply_filters()
        self.update_status(f"{preset_name} cilt rötuş uygulandı.")

    def inpaint_with_opencv(self, pil_img, mask_u8, radius):
        import numpy as np
        import cv2

        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        mask_u8 = mask_u8.astype("uint8")
        mode = "CPU"

        use_gpu = bool(self.gpu_accel_var.get())
        if use_gpu and hasattr(cv2, "cuda"):
            try:
                if cv2.cuda.getCudaEnabledDeviceCount() > 0 and hasattr(cv2.cuda, "inpaint"):
                    gpu_src = cv2.cuda_GpuMat()
                    gpu_mask = cv2.cuda_GpuMat()
                    gpu_src.upload(bgr)
                    gpu_mask.upload(mask_u8)
                    gpu_out = cv2.cuda.inpaint(gpu_src, gpu_mask, float(radius), cv2.INPAINT_TELEA)
                    bgr_out = gpu_out.download()
                    mode = "GPU"
                else:
                    bgr_out = cv2.inpaint(bgr, mask_u8, float(radius), cv2.INPAINT_TELEA)
            except Exception:
                bgr_out = cv2.inpaint(bgr, mask_u8, float(radius), cv2.INPAINT_TELEA)
        else:
            bgr_out = cv2.inpaint(bgr, mask_u8, float(radius), cv2.INPAINT_TELEA)

        out_img = Image.fromarray(cv2.cvtColor(bgr_out, cv2.COLOR_BGR2RGB))
        return out_img, mode

    def sync_zoom_controls(self):
        if self.zoom_slider is not None:
            self.zoom_slider.set(self.zoom_level)
        if self.zoom_value_label is not None:
            self.zoom_value_label.configure(text=f"{int(self.zoom_level * 100)}%")

    def on_zoom_slider(self, value):
        if self.processed_image is None:
            if self.zoom_slider is not None:
                self.zoom_slider.set(self.zoom_level)
            return
        self.zoom_level = max(0.1, min(float(value), 5.0))
        if self.zoom_level <= 1.0:
            self.pan_x = 0.0
            self.pan_y = 0.0
        self.sync_zoom_controls()
        self.update_view()

    def on_heal_brush_size_change(self, value):
        self.heal_brush_size = int(float(value))
        if hasattr(self, "heal_brush_value_label") and self.heal_brush_value_label is not None:
            self.heal_brush_value_label.configure(text=f"{self.heal_brush_size}px")

    def start_add_text(self):
        if self.raw_image is None:
            return
        selection_box = self.get_selection_box()
        if selection_box is None:
            messagebox.showwarning("Uyarı", "Önce metin alanını seçin.")
            return
        text = simpledialog.askstring("Yazı Ekle", "Yazıyı girin:")
        if not text:
            return
        color = colorchooser.askcolor(title="Yazı Rengi Seç", color=self.last_text_color)
        if not color or not color[1]:
            return
        self.last_text_color = color[1]
        self.heal_brush_mode = False
        left, top, right, bottom = [int(v) for v in selection_box]
        box_w = max(20, right - left)
        box_h = max(20, bottom - top)
        size = self.calculate_font_size_for_box(text, box_w, box_h, is_emoji=False)
        self.pending_insert = {
            "type": "text",
            "value": text,
            "size": int(size),
            "x": left,
            "y": top,
            "color": self.last_text_color,
        }
        self.refresh_pending_insert_overlay()
        self.update_status("Yazı hazır. Sürükleyin, sonra 'Yazı/Emoji Uygula'.")

    def start_add_emoji(self):
        if self.raw_image is None:
            return
        selection_box = self.get_selection_box()
        if selection_box is None:
            messagebox.showwarning("Uyarı", "Önce emoji alanını seçin.")
            return
        emoji = simpledialog.askstring("Emoji Ekle", "Emoji girin (örn: 😀 ❤️ 🔥):")
        if not emoji:
            return
        color = colorchooser.askcolor(title="Emoji Rengi Seç (opsiyonel)", color=self.last_text_color)
        chosen_color = self.last_text_color
        if color and color[1]:
            chosen_color = color[1]
            self.last_text_color = chosen_color
        self.heal_brush_mode = False
        left, top, right, bottom = [int(v) for v in selection_box]
        box_w = max(20, right - left)
        box_h = max(20, bottom - top)
        size = self.calculate_font_size_for_box(emoji, box_w, box_h, is_emoji=True)
        self.pending_insert = {
            "type": "emoji",
            "value": emoji,
            "size": int(size),
            "x": left,
            "y": top,
            "color": chosen_color,
        }
        self.refresh_pending_insert_overlay()
        self.update_status("Emoji hazır. Sürükleyin, sonra 'Yazı/Emoji Uygula'.")

    def get_font_for_insert(self, size, is_emoji):
        if is_emoji:
            candidates = [
                r"C:\Windows\Fonts\seguiemj.ttf",
                r"C:\Windows\Fonts\Segoe UI Emoji.ttf",
                "seguiemj.ttf",
                "Segoe UI Emoji.ttf",
                "NotoColorEmoji.ttf",
            ]
        else:
            candidates = [
                r"C:\Windows\Fonts\arial.ttf",
                r"C:\Windows\Fonts\segoeui.ttf",
                r"C:\Windows\Fonts\tahoma.ttf",
                "arial.ttf",
                "segoeui.ttf",
                "Tahoma.ttf",
            ]
        for name in candidates:
            try:
                return ImageFont.truetype(name, int(size))
            except Exception:
                continue
        return ImageFont.load_default()

    def calculate_font_size_for_box(self, text, box_w, box_h, is_emoji):
        probe_img = Image.new("RGB", (max(10, box_w), max(10, box_h)), (0, 0, 0))
        draw = ImageDraw.Draw(probe_img)
        low, high = 8, 280
        best = 12
        while low <= high:
            mid = (low + high) // 2
            font = self.get_font_for_insert(mid, is_emoji)
            x1, y1, x2, y2 = draw.textbbox((0, 0), text, font=font)
            tw, th = (x2 - x1), (y2 - y1)
            if tw <= box_w and th <= box_h:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best

    def remove_last_annotation(self):
        if self.text_layers:
            self.push_undo_state()
            self.text_layers.pop()
            self.selected_layer_index = len(self.text_layers) - 1
            self.refresh_layer_menu()
            self.apply_filters()
            self.update_status("Son yazı/emoji katmanı silindi.")
            return
        if not self.annotation_snapshots:
            self.update_status("Silinecek yazı/emoji yok.")
            return
        snapshot = self.annotation_snapshots.pop()
        self.restore_state(snapshot, "Son yazı/emoji silindi.")

    def cancel_pending_insert(self):
        self.pending_insert = None
        if self.pending_insert_canvas_id is not None:
            self.canvas.delete(self.pending_insert_canvas_id)
            self.pending_insert_canvas_id = None
        self.pending_insert_drag_offset = None
        self.update_status("Yazı/emoji iptal edildi.")

    def image_to_canvas_coords(self, img_x, img_y):
        if self.processed_image is None:
            return None
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        img_w, img_h = self.processed_image.size
        ratio = min(cw / img_w, ch / img_h)
        nw = img_w * ratio * self.zoom_level
        nh = img_h * ratio * self.zoom_level
        if nw <= 0 or nh <= 0:
            return None
        off_x = (cw - nw) / 2 + self.pan_x
        off_y = (ch - nh) / 2 + self.pan_y
        scale = nw / img_w
        return off_x + (img_x * scale), off_y + (img_y * scale)

    def refresh_pending_insert_overlay(self):
        if self.pending_insert is None:
            return
        pos = self.image_to_canvas_coords(self.pending_insert["x"], self.pending_insert["y"])
        if pos is None:
            return
        if self.pending_insert_canvas_id is not None:
            self.canvas.delete(self.pending_insert_canvas_id)
            self.pending_insert_canvas_id = None
        is_emoji = self.pending_insert["type"] == "emoji"
        if self.processed_image is not None:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            img_w, img_h = self.processed_image.size
            ratio = min(cw / img_w, ch / img_h)
            display_scale = ratio * self.zoom_level
        else:
            display_scale = 1.0
        scale_font = max(10, int(self.pending_insert["size"] * display_scale))
        if is_emoji:
            font = ("Segoe UI Emoji", scale_font)
        else:
            font = ("Arial", scale_font)
        self.pending_insert_canvas_id = self.canvas.create_text(
            pos[0],
            pos[1],
            text=self.pending_insert["value"],
            fill=self.pending_insert.get("color", "#FFFFFF"),
            anchor="nw",
            font=font,
        )

    def apply_pending_insert(self):
        if self.pending_insert is None or self.processed_image is None:
            self.update_status("Uygulanacak yazı/emoji yok.")
            return
        self.push_undo_state()
        layer = dict(self.pending_insert)
        layer["font_family"] = self.text_font_var.get()
        layer["bold"] = bool(self.text_bold_var.get())
        layer["italic"] = bool(self.text_italic_var.get())
        layer["opacity"] = float(self.text_opacity_slider.get())
        layer["stroke"] = int(round(float(self.text_stroke_slider.get())))
        self.text_layers.append(layer)
        self.selected_layer_index = len(self.text_layers) - 1
        self.refresh_layer_menu()
        self.cancel_pending_insert()
        self.apply_filters()
        self.update_status("Yazı/emoji katman olarak eklendi.")

    def toggle_heal_brush_mode(self):
        if self.raw_image is None:
            return
        self.heal_brush_mode = not self.heal_brush_mode
        if self.heal_brush_mode:
            self.clear_selection()
            self.update_status("Leke fırça modu açık. Boyayın, Enter ile uygula.")
        else:
            self.clear_heal_overlay()
            self.update_status("Leke fırça modu kapalı.")

    def clear_heal_overlay(self):
        for overlay_id in self.heal_overlay_ids:
            self.canvas.delete(overlay_id)
        self.heal_overlay_ids = []
        self.heal_mask_points = []
        if self.heal_brush_mode:
            self.update_status("Leke maskesi temizlendi.")

    def bind_shortcuts(self):
        self.bind_all("<Control-o>", lambda e: self.open_file_dialog())
        self.bind_all("<Control-s>", lambda e: self.save_current_file())
        self.bind_all("<Control-Shift-S>", lambda e: self.save_as_dialog())
        self.bind_all("<Control-c>", lambda e: self.copy_to_clipboard())
        self.bind_all("<Control-v>", lambda e: self.paste_from_clipboard())
        self.bind_all("<Control-Shift-C>", lambda e: self.copy_selection())
        self.bind_all("<Control-Shift-X>", lambda e: self.crop_to_selection())
        self.bind_all("<Control-Shift-Delete>", lambda e: self.remove_selection_content())
        self.bind_all("<Control-z>", lambda e: self.undo_action())
        self.bind_all("<Control-y>", lambda e: self.redo_action())
        self.bind_all("<Delete>", lambda e: self.clear_selection("Seçim temizlendi."))
        self.bind_all("<b>", lambda e: self.toggle_heal_brush_mode())
        self.bind_all("<Return>", lambda e: self.apply_heal_brush())
        self.bind_all("<Escape>", lambda e: self.clear_heal_overlay())

    def get_slider_values(self):
        return {name: slider.get() for name, slider in self.sliders.items()}

    def set_slider_values(self, values):
        self._suspend_history = True
        try:
            for name, slider in self.sliders.items():
                slider.set(values.get(name, self.slider_defaults.get(name, 1.0)))
        finally:
            self._suspend_history = False

    def get_state_snapshot(self):
        return {
            "raw_image": self.raw_image.copy() if self.raw_image is not None else None,
            "current_path": self.current_path,
            "source_name": self.source_name,
            "folder_images": list(self.folder_images),
            "rotation_angle": self.rotation_angle,
            "zoom_level": self.zoom_level,
            "slider_values": self.get_slider_values(),
            "text_layers": [dict(layer) for layer in self.text_layers],
            "selected_layer_index": self.selected_layer_index,
        }

    def push_undo_state(self):
        if self.raw_image is None or self._suspend_history:
            return
        self.undo_stack.append(self.get_state_snapshot())
        if len(self.undo_stack) > self.history_limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def push_snapshot_to_undo(self, snapshot):
        if snapshot is None or self._suspend_history:
            return
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self.history_limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def restore_state(self, snapshot, status_text):
        self._suspend_history = True
        try:
            self.raw_image = snapshot["raw_image"].copy() if snapshot["raw_image"] is not None else None
            self.current_path = snapshot["current_path"]
            self.source_name = snapshot["source_name"]
            self.folder_images = list(snapshot["folder_images"])
            self.rotation_angle = snapshot["rotation_angle"]
            self.zoom_level = snapshot["zoom_level"]
            self.set_slider_values(snapshot["slider_values"])
            self.text_layers = [dict(layer) for layer in snapshot.get("text_layers", [])]
            self.selected_layer_index = snapshot.get("selected_layer_index", -1)
            self.refresh_layer_menu()
            self.clear_selection()
            if self.raw_image is not None:
                self.apply_filters()
                title_name = self.source_name or "Görsel"
                self.update_meta(title_name, self.raw_image.width, self.raw_image.height)
                self.set_image_actions_enabled(True)
            else:
                self.processed_image = None
                self.meta_label.configure(text="Resim yüklenmedi")
                self.title("ErheiC Studio Pro - Ultimate Edition @erdal.1.4.26")
                self.set_image_actions_enabled(False)
            self.update_status(status_text)
        finally:
            self._suspend_history = False

    def undo_action(self):
        if not self.undo_stack or self.raw_image is None:
            self.update_status("Geri alınacak işlem yok.")
            return
        self.redo_stack.append(self.get_state_snapshot())
        snapshot = self.undo_stack.pop()
        self.restore_state(snapshot, "Son işlem geri alındı.")

    def redo_action(self):
        if not self.redo_stack or self.raw_image is None:
            self.update_status("Yinelenecek işlem yok.")
            return
        self.undo_stack.append(self.get_state_snapshot())
        snapshot = self.redo_stack.pop()
        self.restore_state(snapshot, "İşlem yeniden uygulandı.")

    def clear_selection(self, status_text=None):
        if self.selection_rect is not None:
            self.canvas.delete(self.selection_rect)
            self.selection_rect = None
        self.selection_coords = None
        self.start_x = None
        self.start_y = None
        if status_text is not None:
            self.update_status(status_text)

    def update_meta(self, source_name, width, height):
        self.meta_label.configure(text=f"Dosya: {source_name}\nBoyut: {width}x{height}")
        self.title(f"ErheiC Studio - {source_name}")

    def load_image(self, path):
        if not path:
            return

        try:
            path = path.replace('"', "").strip()
            if not os.path.exists(path):
                messagebox.showwarning("Uyarı", "Dosya bulunamadı.")
                return

            self.current_path = os.path.abspath(path)
            self.source_name = os.path.basename(path)
            with Image.open(self.current_path) as opened_image:
                img = ImageOps.exif_transpose(opened_image)
                self.raw_image = img.convert("RGB")

            self.rotation_angle = 0
            self.zoom_level = 1.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.annotation_snapshots.clear()
            self.pending_insert = None
            self.text_layers = []
            self.selected_layer_index = -1
            self.refresh_layer_menu()
            self.set_slider_values(dict(self.slider_defaults))
            self.preset_var.set("Preset: Yok")
            self.skin_preset_var.set("Cilt Rötuş: Yok")
            self.sync_zoom_controls()

            self.clear_selection("Seçim temizlendi.")
            self.update_folder_list(self.current_path)
            self.apply_filters()
            self.update_meta(self.source_name, self.raw_image.width, self.raw_image.height)
            self.set_image_actions_enabled(True)
            self.update_status("Görsel yüklendi.")
        except Exception as exc:
            messagebox.showerror("Hata", f"Yükleme hatası: {exc}")

    def apply_filters(self, _=None):
        if self.raw_image is None:
            return

        img = self.raw_image.rotate(self.rotation_angle, expand=True)
        img = ImageEnhance.Brightness(img).enhance(self.sliders["Parlaklık"].get())
        img = ImageEnhance.Contrast(img).enhance(self.sliders["Kontrast"].get())
        img = ImageEnhance.Sharpness(img).enhance(self.sliders["Keskinlik"].get())
        img = ImageEnhance.Color(img).enhance(self.sliders["Doygunluk"].get())

        exposure = self.sliders["Exposure"].get()
        if abs(exposure) > 0.01:
            img = ImageEnhance.Brightness(img).enhance(2 ** exposure)

        temperature = self.sliders["Temperature"].get()
        tint = self.sliders["Tint"].get()
        img = self.apply_temperature_tint(img, temperature, tint)

        vibrance = self.sliders["Vibrance"].get()
        if abs(vibrance) > 0.1:
            img = ImageEnhance.Color(img).enhance(1.0 + (vibrance / 180.0))

        clarity = self.sliders["Clarity"].get()
        if clarity > 0:
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=int(clarity * 1.6), threshold=3))
        elif clarity < 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=min(2.0, abs(clarity) / 50.0)))

        dehaze = self.sliders["Dehaze"].get()
        if abs(dehaze) > 0.1:
            img = ImageEnhance.Contrast(img).enhance(1.0 + (dehaze / 180.0))
            img = ImageEnhance.Brightness(img).enhance(1.0 - (dehaze / 500.0))

        if self.text_layers:
            draw = ImageDraw.Draw(img, "RGBA")
            for layer in self.text_layers:
                is_emoji = layer.get("type") == "emoji"
                font = self.get_font_for_insert(layer.get("size", 24), is_emoji)
                txt = layer.get("value", "")
                x = int(layer.get("x", 0))
                y = int(layer.get("y", 0))
                color = layer.get("color", "#FFFFFF")
                opacity = max(0.1, min(1.0, float(layer.get("opacity", 1.0))))
                stroke = max(0, int(layer.get("stroke", 1)))
                bold = bool(layer.get("bold", False))
                alpha = int(255 * opacity)
                fill_rgba = self.hex_to_rgba(color, alpha)
                shadow_rgba = (0, 0, 0, max(90, int(alpha * 0.55)))
                draw.text((x + 2, y + 2), txt, font=font, fill=shadow_rgba, anchor="lt")
                # pseudo-bold by drawing twice with tiny offset
                draw.text((x, y), txt, font=font, fill=fill_rgba, anchor="lt", stroke_width=stroke, stroke_fill=(0, 0, 0, alpha))
                if bold:
                    draw.text((x + 1, y), txt, font=font, fill=fill_rgba, anchor="lt", stroke_width=stroke, stroke_fill=(0, 0, 0, alpha))

        self.processed_image = img
        self.update_view()

    def update_view(self):
        if self.processed_image is None:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        img_w, img_h = self.processed_image.size
        ratio = min(cw / img_w, ch / img_h)

        nw = max(1, int(img_w * ratio * self.zoom_level))
        nh = max(1, int(img_h * ratio * self.zoom_level))
        self.rendered_image_size = (nw, nh)

        max_pan_x = max(0.0, (nw - cw) / 2)
        max_pan_y = max(0.0, (nh - ch) / 2)
        self.pan_x = max(-max_pan_x, min(self.pan_x, max_pan_x))
        self.pan_y = max(-max_pan_y, min(self.pan_y, max_pan_y))

        resized_img = self.processed_image.resize((nw, nh), Image.Resampling.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(resized_img)

        self.canvas.delete("all")
        self.selection_rect = None
        self.selection_coords = None
        self.start_x = None
        self.start_y = None
        center_x = (cw / 2) + self.pan_x
        center_y = (ch / 2) + self.pan_y
        self.canvas.create_image(center_x, center_y, image=self.tk_img, anchor="center")
        self.display_image_bbox = (
            center_x - (nw / 2),
            center_y - (nh / 2),
            center_x + (nw / 2),
            center_y + (nh / 2),
        )
        self.refresh_pending_insert_overlay()
        self.update_vertical_scrollbar(cw, ch, nw, nh)
        self.update_horizontal_scrollbar(cw, ch, nw, nh)

    def update_vertical_scrollbar(self, cw, ch, nw, nh):
        if nh <= ch:
            self.v_scrollbar.set(0.0, 1.0)
            self.v_scrollbar.grid_remove()
            return

        overflow = nh - ch
        view_ratio = ch / nh
        top_px = max(0.0, min(overflow, (overflow / 2) - self.pan_y))
        start = top_px / nh
        end = min(1.0, start + view_ratio)
        self.v_scrollbar.set(start, end)
        self.v_scrollbar.grid()

    def on_vertical_scroll(self, action, value, _unused=None):
        if self.processed_image is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        nw, nh = self.rendered_image_size
        if cw < 10 or ch < 10 or nh <= ch:
            return

        max_pan_y = (nh - ch) / 2
        if action == "moveto":
            frac = float(value)
            frac = max(0.0, min(frac, 1.0))
            top_px = min(nh - ch, frac * nh)
            self.pan_y = max_pan_y - top_px
        elif action == "scroll":
            units = int(value)
            self.pan_y += units * -40
        self.update_view()

    def update_horizontal_scrollbar(self, cw, ch, nw, nh):
        if nw <= cw:
            self.h_scrollbar.set(0.0, 1.0)
            self.h_scrollbar.grid_remove()
            return

        overflow = nw - cw
        view_ratio = cw / nw
        left_px = max(0.0, min(overflow, (overflow / 2) - self.pan_x))
        start = left_px / nw
        end = min(1.0, start + view_ratio)
        self.h_scrollbar.set(start, end)
        self.h_scrollbar.grid()

    def on_horizontal_scroll(self, action, value, _unused=None):
        if self.processed_image is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        nw, nh = self.rendered_image_size
        if cw < 10 or ch < 10 or nw <= cw:
            return

        max_pan_x = (nw - cw) / 2
        if action == "moveto":
            frac = float(value)
            frac = max(0.0, min(frac, 1.0))
            left_px = min(nw - cw, frac * nw)
            self.pan_x = max_pan_x - left_px
        elif action == "scroll":
            units = int(value)
            self.pan_x += units * -40
        self.update_view()

    def on_start_selection(self, event):
        if self.processed_image is None:
            return
        if self.pending_insert is not None:
            pt = self.canvas_to_image_coords(event.x, event.y)
            if pt is not None:
                # Yazı/emoji aktifken tıklayıp sürüklemeyi daha kolay hale getir.
                self.pending_insert_drag_offset = (
                    pt[0] - self.pending_insert["x"],
                    pt[1] - self.pending_insert["y"],
                )
            return
        if self.heal_brush_mode:
            self.clear_heal_overlay()
            self.add_heal_brush_point(event.x, event.y)
            return

        self.clear_selection()
        self.start_x = event.x
        self.start_y = event.y
        self.selection_rect = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="#3B8ED0",
            width=2,
            dash=(4, 4),
        )
        self.selection_coords = (self.start_x, self.start_y, self.start_x, self.start_y)
        self.update_status("Seçim başlatıldı.")

    def on_drag_selection(self, event):
        if self.pending_insert is not None and self.pending_insert_drag_offset is not None:
            pt = self.canvas_to_image_coords(event.x, event.y)
            if pt is not None:
                self.pending_insert["x"] = pt[0] - self.pending_insert_drag_offset[0]
                self.pending_insert["y"] = pt[1] - self.pending_insert_drag_offset[1]
                self.refresh_pending_insert_overlay()
            return
        if self.heal_brush_mode and self.processed_image is not None:
            self.add_heal_brush_point(event.x, event.y)
            return
        if self.selection_rect is not None and self.start_x is not None and self.start_y is not None:
            self.canvas.coords(self.selection_rect, self.start_x, self.start_y, event.x, event.y)
            self.selection_coords = (self.start_x, self.start_y, event.x, event.y)
            width = abs(event.x - self.start_x)
            height = abs(event.y - self.start_y)
            self.update_status(f"Seçim: {width} x {height} px")

    def on_end_selection(self, event):
        if self.pending_insert is not None:
            self.pending_insert_drag_offset = None
            return
        if self.heal_brush_mode and self.processed_image is not None:
            self.add_heal_brush_point(event.x, event.y)
            self.update_status("Leke maskesi hazır. Enter ile uygula, Esc ile temizle.")
            return
        if self.start_x is None or self.start_y is None:
            return

        end_x = event.x
        end_y = event.y
        width = abs(end_x - self.start_x)
        height = abs(end_y - self.start_y)

        if width < self.min_selection_size or height < self.min_selection_size:
            self.clear_selection(
                f"Seçim çok küçük. En az {self.min_selection_size} x {self.min_selection_size} px olmalı."
            )
            return

        self.selection_coords = (self.start_x, self.start_y, end_x, end_y)
        self.update_status(f"Seçim hazır: {width} x {height} px")

    def on_slider_press(self, _event):
        if self.raw_image is None or self._suspend_history:
            return
        self.pending_slider_snapshot = self.get_state_snapshot()

    def on_slider_release(self, _event):
        if self.raw_image is None or self._suspend_history:
            return
        self.push_snapshot_to_undo(self.pending_slider_snapshot)
        self.pending_slider_snapshot = None
        self.update_status("Filtre ayarı kaydedildi.")

    def get_selection_box(self):
        if self.processed_image is None or self.selection_coords is None:
            return None

        coords = self.selection_coords
        if len(coords) < 4:
            return None

        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        img_w, img_h = self.processed_image.size
        ratio = min(cw / img_w, ch / img_h)
        nw = img_w * ratio * self.zoom_level
        nh = img_h * ratio * self.zoom_level
        if nw <= 0 or nh <= 0:
            return None

        off_x = (cw - nw) / 2 + self.pan_x
        off_y = (ch - nh) / 2 + self.pan_y
        x_min = min(coords[0], coords[2]) - off_x
        y_min = min(coords[1], coords[3]) - off_y
        x_max = max(coords[0], coords[2]) - off_x
        y_max = max(coords[1], coords[3]) - off_y

        scale = img_w / nw
        real_left = max(0, x_min * scale)
        real_top = max(0, y_min * scale)
        real_right = min(img_w, x_max * scale)
        real_bottom = min(img_h, y_max * scale)

        if real_right <= real_left or real_bottom <= real_top:
            return None
        return real_left, real_top, real_right, real_bottom

    def canvas_to_image_coords(self, canvas_x, canvas_y):
        if self.processed_image is None:
            return None
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        img_w, img_h = self.processed_image.size
        ratio = min(cw / img_w, ch / img_h)
        nw = img_w * ratio * self.zoom_level
        nh = img_h * ratio * self.zoom_level
        if nw <= 0 or nh <= 0:
            return None
        off_x = (cw - nw) / 2 + self.pan_x
        off_y = (ch - nh) / 2 + self.pan_y
        rel_x = canvas_x - off_x
        rel_y = canvas_y - off_y
        if rel_x < 0 or rel_y < 0 or rel_x > nw or rel_y > nh:
            return None
        scale = img_w / nw
        return int(rel_x * scale), int(rel_y * scale)

    def add_heal_brush_point(self, canvas_x, canvas_y):
        pt = self.canvas_to_image_coords(canvas_x, canvas_y)
        if pt is None:
            return
        self.heal_mask_points.append(pt)
        radius = max(2, int((self.heal_brush_size * self.zoom_level) / 2))
        overlay_id = self.canvas.create_oval(
            canvas_x - radius,
            canvas_y - radius,
            canvas_x + radius,
            canvas_y + radius,
            outline="#ff4d4d",
            fill="#ff4d4d",
            stipple="gray50",
            width=1,
        )
        self.heal_overlay_ids.append(overlay_id)

    def apply_heal_brush(self):
        if not self.heal_mask_points:
            if self.heal_brush_mode:
                self.update_status("Leke maskesi boş.")
            return
        img = self.processed_image.copy()
        img_w, img_h = img.size

        try:
            import numpy as np

            self.push_undo_state()
            mask = np.zeros((img_h, img_w), dtype=np.uint8)
            brush_radius = max(2, self.heal_brush_size // 2)
            for x, y in self.heal_mask_points:
                rr = brush_radius
                y0, y1 = max(0, y - rr), min(img_h, y + rr + 1)
                x0, x1 = max(0, x - rr), min(img_w, x + rr + 1)
                yy, xx = np.ogrid[y0:y1, x0:x1]
                circle = (xx - x) ** 2 + (yy - y) ** 2 <= rr ** 2
                mask[y0:y1, x0:x1][circle] = 255

            radius = float(max(3, min(12, brush_radius * 0.6)))
            img, mode_used = self.inpaint_with_opencv(img, mask, radius)
        except Exception:
            self.clear_heal_overlay()
            self.update_status("Leke fırça için OpenCV gerekli.")
            messagebox.showwarning("Uyarı", "Leke fırça için kurulum gerekli:\npip install opencv-python numpy")
            return

        self.raw_image = img.convert("RGB")
        self.current_path = None
        self.source_name = f"{self.source_name or 'Gorsel'} - LekeFirca"
        self.folder_images = []
        self.rotation_angle = 0
        self.zoom_level = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.set_slider_values(dict(self.slider_defaults))
        self.preset_var.set("Preset: Yok")
        self.skin_preset_var.set("Cilt Rötuş: Yok")
        self.sync_zoom_controls()
        self.clear_heal_overlay()
        self.apply_filters()
        self.update_meta(self.source_name, self.raw_image.width, self.raw_image.height)
        self.update_status(f"Leke fırça uygulandı ({mode_used}).")

    def copy_selection(self):
        if self.processed_image is None:
            # messagebox.showwarning("Uyarı", "Önce bir görsel yükleyin.")
            return

        if self.selection_coords is None:
            messagebox.showwarning("Uyarı", "Lütfen önce fareyle bir alan seçin.")
            return

        try:
            selection_box = self.get_selection_box()
            if selection_box is None:
                self.update_status("Seçim kopyalanamadı.")
                messagebox.showwarning("Uyarı", "Geçerli bir seçim alanı bulunamadı.")
                return

            cropped = self.processed_image.crop(selection_box)
            self.send_to_clipboard(cropped)
            self.update_status("Seçili alan panoya kopyalandı.")
            messagebox.showinfo("Başarılı", "Seçili alan panoya kopyalandı.")
        except Exception as exc:
            self.update_status("Seçim kopyalanırken hata oluştu.")
            messagebox.showerror("Hata", f"Seçim kopyalanırken hata oluştu: {exc}")

    def crop_to_selection(self):
        if self.processed_image is None:
            # messagebox.showwarning("Uyarı", "Önce bir görsel yükleyin.")
            return
        if self.selection_coords is None:
            messagebox.showwarning("Uyarı", "Lütfen önce fareyle bir alan seçin.")
            return

        selection_box = self.get_selection_box()
        if selection_box is None:
            self.update_status("Kırpma için geçerli seçim bulunamadı.")
            messagebox.showwarning("Uyarı", "Geçerli bir seçim alanı bulunamadı.")
            return

        self.push_undo_state()
        self.raw_image = self.processed_image.crop(selection_box).convert("RGB")
        self.current_path = None
        self.source_name = f"{self.source_name or 'Gorsel'} - Kirpilmis"
        self.folder_images = []
        self.rotation_angle = 0
        self.zoom_level = 1.0
        self.set_slider_values({name: 1.0 for name in self.sliders})
        self.clear_selection("Görsel seçime göre kırpıldı.")
        self.apply_filters()
        self.update_meta(self.source_name, self.raw_image.width, self.raw_image.height)

    def remove_selection_content(self):
        if self.processed_image is None:
            return
        if self.selection_coords is None:
            messagebox.showwarning("Uyarı", "Lütfen önce fareyle bir alan seçin.")
            return

        selection_box = self.get_selection_box()
        if selection_box is None:
            self.update_status("Silme için geçerli seçim bulunamadı.")
            messagebox.showwarning("Uyarı", "Geçerli bir seçim alanı bulunamadı.")
            return

        img = self.processed_image.copy()
        left, top, right, bottom = [int(v) for v in selection_box]
        sel_w = max(1, right - left)
        sel_h = max(1, bottom - top)
        img_w, img_h = img.size

        # 1) Öncelik: OpenCV Telea inpaint (daha Photoshop-benzeri sonuç).
        # 2) OpenCV yoksa mevcut yumuşak komşu doku yöntemiyle devam.
        used_opencv = False
        try:
            import numpy as np
            mask = np.zeros((img_h, img_w), dtype=np.uint8)
            mask[top:bottom, left:right] = 255

            # Biraz genişletip kenar izi riskini azalt.
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=1)

            radius = float(max(3, min(10, int(min(sel_w, sel_h) * 0.18))))
            self.push_undo_state()
            img, mode_used = self.inpaint_with_opencv(img, mask, radius)
            used_opencv = True
        except Exception:
            src = None
            if top - sel_h >= 0:
                src = img.crop((left, top - sel_h, right, top))
            elif bottom + sel_h <= img_h:
                src = img.crop((left, bottom, right, bottom + sel_h))
            elif left - sel_w >= 0:
                src = img.crop((left - sel_w, top, left, bottom))
            elif right + sel_w <= img_w:
                src = img.crop((right, top, right + sel_w, bottom))

            if src is None:
                fill_color = img.resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
                src = Image.new("RGB", (sel_w, sel_h), fill_color)
            else:
                src = src.resize((sel_w, sel_h), Image.Resampling.LANCZOS)

            feather = max(8, min(sel_w, sel_h) // 6)
            local_mask = Image.new("L", (sel_w, sel_h), 255).filter(ImageFilter.GaussianBlur(radius=feather / 2))
            img.paste(src, (left, top), local_mask)

        self.raw_image = img.convert("RGB")
        self.current_path = None
        self.source_name = f"{self.source_name or 'Gorsel'} - AkilliSil"
        self.folder_images = []
        self.rotation_angle = 0
        self.zoom_level = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.set_slider_values(dict(self.slider_defaults))
        self.preset_var.set("Preset: Yok")
        self.skin_preset_var.set("Cilt Rötuş: Yok")
        self.sync_zoom_controls()
        if used_opencv:
            self.clear_selection(f"Seçili alan akıllı şekilde silindi ({mode_used}).")
        else:
            self.clear_selection("Seçili alan silindi (temel mod).")
        self.apply_filters()
        self.update_meta(self.source_name, self.raw_image.width, self.raw_image.height)

    def reset_filters(self):
        if self.raw_image is None:
            return

        self.push_undo_state()
        self.set_slider_values(dict(self.slider_defaults))
        self.preset_var.set("Preset: Yok")
        self.skin_preset_var.set("Cilt Rötuş: Yok")
        self.rotation_angle = 0
        self.zoom_level = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.sync_zoom_controls()
        self.clear_selection("Filtreler sıfırlandı.")
        self.apply_filters()

    def rotate_image(self, angle):
        if self.raw_image is None:
            return

        self.push_undo_state()
        self.rotation_angle = (self.rotation_angle + angle) % 360
        self.clear_selection("Görsel döndürüldü.")
        self.apply_filters()

    def flip_image(self):
        if self.raw_image is None:
            return

        self.push_undo_state()
        self.raw_image = ImageOps.mirror(self.raw_image)
        self.clear_selection("Görsel aynalandı.")
        self.apply_filters()

    def convert_image(self, format_type):
        img = self.get_active_image()
        if img is None:
            return

        ext = format_type.lower()
        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            filetypes=[(f"{format_type} Files", f"*.{ext}")],
        )
        if not path:
            return

        try:
            if format_type == "ICO":
                img.save(path, format="ICO", sizes=[(256, 256)])
            elif format_type == "PDF":
                img.save(path, "PDF", resolution=100.0)
            elif format_type == "PNG":
                img.save(path, format="PNG")
            else:
                img.save(path, format=format_type, quality=95)
            self.update_status(f"Görsel {format_type} olarak kaydedildi.")
            messagebox.showinfo("Başarılı", "Kaydedildi.")
        except Exception as exc:
            messagebox.showerror("Hata", str(exc))

    def save_as_dialog(self):
        img = self.get_active_image()
        if img is None:
            return

        filetypes = [
            ("JPEG", "*.jpg *.jpeg"),
            ("PNG", "*.png"),
            ("BMP", "*.bmp"),
            ("WEBP", "*.webp"),
            ("ICO", "*.ico"),
            ("PDF", "*.pdf"),
            ("Tüm Dosyalar", "*.*"),
        ]
        path = filedialog.asksaveasfilename(
            title="Farklı Kaydet",
            defaultextension=".png",
            filetypes=filetypes,
        )
        if not path:
            return

        self.save_to_path(path)

    def save_current_file(self):
        img = self.get_active_image()
        if img is None:
            return

        if not self.current_path:
            self.save_as_dialog()
            return

        ext = Path(self.current_path).suffix.lower()
        if ext == ".heic":
            self.update_status("HEIC dosyası doğrudan üzerine yazılamaz. Farklı Kaydet açıldı.")
            messagebox.showinfo("Bilgi", "HEIC dosyası doğrudan kaydedilemiyor. Lütfen Farklı Kaydet ile dışa aktarın.")
            self.save_as_dialog()
            return

        self.save_to_path(self.current_path)

    def save_to_path(self, path):
        img = self.get_active_image()
        if img is None:
            return

        ext = Path(path).suffix.lower()
        try:
            if ext in (".jpg", ".jpeg"):
                img.save(path, format="JPEG", quality=95)
            elif ext == ".png":
                img.save(path, format="PNG")
            elif ext == ".bmp":
                img.save(path, format="BMP")
            elif ext == ".webp":
                img.save(path, format="WEBP", quality=95)
            elif ext == ".ico":
                img.save(path, format="ICO", sizes=[(256, 256)])
            elif ext == ".pdf":
                img.save(path, format="PDF", resolution=100.0)
            else:
                # Bilinmeyen uzantılarda PNG olarak güvenli kaydet
                path = f"{path}.png"
                img.save(path, format="PNG")

            self.current_path = os.path.abspath(path)
            self.source_name = os.path.basename(path)
            self.update_meta(self.source_name, img.width, img.height)
            self.update_folder_list(self.current_path)
            self.update_status("Dosya kaydedildi.")
        except Exception as exc:
            messagebox.showerror("Kaydetme Hatası", str(exc))

    def on_mouse_wheel(self, event):
        if self.processed_image is None:
            return
        if self.display_image_bbox is None:
            return
        x1, y1, x2, y2 = self.display_image_bbox
        if not (x1 <= event.x <= x2 and y1 <= event.y <= y2):
            return

        ctrl_pressed = bool(event.state & 0x0004)
        shift_pressed = bool(event.state & 0x0001)
        nw, nh = self.rendered_image_size
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        if shift_pressed and nw > cw:
            step = 40
            self.pan_x += -step if event.delta > 0 else step
            self.update_view()
            return

        if self.zoom_level > 1.0 and nh > ch and not ctrl_pressed:
            step = 40
            self.pan_y += -step if event.delta > 0 else step
            self.update_view()
            return

        self.zoom_level *= 1.1 if event.delta > 0 else 0.9
        self.zoom_level = max(0.1, min(self.zoom_level, 5.0))
        if self.zoom_level <= 1.0:
            self.pan_x = 0.0
            self.pan_y = 0.0
        self.sync_zoom_controls()
        self.update_view()

    def send_to_clipboard(self, img):
        try:
            output = io.BytesIO()
            img.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]
            output.close()

            import win32clipboard

            for _ in range(5):
                clipboard_open = False
                try:
                    win32clipboard.OpenClipboard()
                    clipboard_open = True
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
                    return
                except Exception:
                    time.sleep(0.1)
                finally:
                    if clipboard_open:
                        try:
                            win32clipboard.CloseClipboard()
                        except Exception:
                            pass

            raise RuntimeError("Pano başka bir uygulama tarafından kullanılıyor.")
        except ImportError:
            messagebox.showwarning("Hata", "Lütfen 'pip install pywin32' kurun.")
        except Exception as exc:
            messagebox.showerror("Pano Hatası", str(exc))

    def copy_to_clipboard(self):
        if self.processed_image is not None:
            self.send_to_clipboard(self.processed_image)
            self.update_status("Görsel panoya kopyalandı.")

    def paste_from_clipboard(self):
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                self.push_undo_state()
                self.raw_image = img.convert("RGB")
                self.current_path = None
                self.source_name = "Panodan Yapıştırılan Görsel"
                self.folder_images = []
                self.rotation_angle = 0
                self.zoom_level = 1.0
                self.pan_x = 0.0
                self.pan_y = 0.0
                self.annotation_snapshots.clear()
                self.pending_insert = None
                self.text_layers = []
                self.selected_layer_index = -1
                self.refresh_layer_menu()
                self.set_slider_values(dict(self.slider_defaults))
                self.preset_var.set("Preset: Yok")
                self.skin_preset_var.set("Cilt Rötuş: Yok")
                self.clear_selection()
                self.apply_filters()
                self.update_meta(self.source_name, self.raw_image.width, self.raw_image.height)
                self.set_image_actions_enabled(True)
                self.update_status("Görsel panodan yapıştırıldı.")
            elif isinstance(img, list) and img:
                self.load_image(img[0])
            else:
                self.update_status("Panoda kullanılabilir görsel yok.")
                messagebox.showwarning("Uyarı", "Panoda kullanılabilir bir görsel bulunamadı.")
        except Exception as exc:
            messagebox.showerror("Hata", str(exc))

    def update_folder_list(self, current_path):
        folder = os.path.dirname(current_path)
        try:
            self.folder_images = [
                os.path.join(folder, filename)
                for filename in os.listdir(folder)
                if filename.lower().endswith(self.supported_exts)
            ]
            self.folder_images.sort()
        except OSError as exc:
            self.folder_images = []
            messagebox.showwarning("Uyarı", f"Klasör içeriği okunamadı: {exc}")

    def navigate(self, direction):
        if not self.current_path or not self.folder_images:
            return

        try:
            idx = self.folder_images.index(self.current_path)
        except ValueError:
            return

        new_idx = (idx + direction) % len(self.folder_images)
        self.load_image(self.folder_images[new_idx])

    def open_file_dialog(self):
        path = filedialog.askopenfilename(
            filetypes=[("Görsel Dosyaları", "*.heic *.jpg *.jpeg *.png *.bmp *.webp *.ico")]
        )
        if path:
            self.load_image(path)

    def print_image(self):
        img = self.get_active_image()
        if img is None:
            return

        try:
            temp_name = f"erheic_print_{int(time.time() * 1000)}.jpg"
            temp_path = os.path.join(tempfile.gettempdir(), temp_name)
            img.save(temp_path, "JPEG", quality=95)
            if sys.platform == "win32":
                os.startfile(temp_path, "print")
                self.update_status("Yazdırma komutu gönderildi.")
            else:
                os.system(f'lpr "{temp_path}"')
                self.update_status("Yazdırma komutu gönderildi.")
        except Exception as exc:
            messagebox.showerror("Hata", str(exc))

    def remove_background_ai(self):
        img = self.get_active_image()
        if img is None:
            return
        try:
            from rembg import remove
            src = io.BytesIO()
            img.save(src, format="PNG")
            result_bytes = remove(src.getvalue())
            result = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
            white_bg = Image.new("RGBA", result.size, (255, 255, 255, 255))
            composited = Image.alpha_composite(white_bg, result).convert("RGB")

            self.push_undo_state()
            self.raw_image = composited
            self.current_path = None
            self.source_name = f"{self.source_name or 'Gorsel'} - ArkaPlanSilindi"
            self.folder_images = []
            self.rotation_angle = 0
            self.zoom_level = 1.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            self.text_layers = []
            self.selected_layer_index = -1
            self.refresh_layer_menu()
            self.set_slider_values(dict(self.slider_defaults))
            self.preset_var.set("Preset: Yok")
            self.skin_preset_var.set("Cilt Rötuş: Yok")
            self.sync_zoom_controls()
            self.clear_selection("AI ile arka plan silindi.")
            self.apply_filters()
            self.update_meta(self.source_name, self.raw_image.width, self.raw_image.height)
        except ImportError:
            messagebox.showwarning("Uyarı", "AI arka plan silme için kurulum gerekli:\npip install rembg onnxruntime")
        except Exception as exc:
            messagebox.showerror("Hata", f"AI arka plan silme hatası: {exc}")

    def check_args(self):
        if len(sys.argv) > 1:
            self.load_image(sys.argv[1])


if __name__ == "__main__":
    app = UniversalPhotoStudio()
    app.mainloop()
