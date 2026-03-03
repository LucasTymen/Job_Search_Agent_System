from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Marges d'impression : 1 cm chaque côté
MARGIN_CM = 1
MARGIN_PT = float(cm) * MARGIN_CM  # 1 cm ≈ 28.35 pt

# Couleurs (ATS-friendly, style discret) : bleu marine + violet/aubergine
COLOR_PRIMARY_HEX = "#000080"    # Bleu marine (intitulés de section)
COLOR_SECONDARY_HEX = "#4B0082"  # Violet/indigo (noms de sociétés)

# Polices : Ubuntu si disponible, sinon Helvetica
def _register_ubuntu_fonts():
    """Enregistre les polices Ubuntu pour un usage dans les Paragraph. Fallback Helvetica."""
    candidates = [
        ("Ubuntu", "Ubuntu-R.ttf"),
        ("Ubuntu-Bold", "Ubuntu-B.ttf"),
        ("Ubuntu-BoldItalic", "Ubuntu-BI.ttf"),
    ]
    base_paths = [
        "/usr/share/fonts/truetype/ubuntu",
        "/usr/share/fonts/truetype/Ubuntu",
        os.path.join(os.path.dirname(__file__), "..", "fonts"),
    ]
    if os.name == "nt":
        base_paths.extend([
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
        ])
    registered = []
    for name, fname in candidates:
        for base in base_paths:
            path = os.path.join(base, fname)
            if os.path.isfile(path):
                try:
                    pdfmetrics.registerFont(TTFont(name, path))
                    registered.append(name)
                    break
                except Exception:
                    pass
    return len(registered) >= 2  # au moins Regular et Bold pour être utile


_UBUNTU_AVAILABLE = _register_ubuntu_fonts()
FONT_FAMILY = "Ubuntu" if _UBUNTU_AVAILABLE else "Helvetica"
FONT_BOLD = "Ubuntu-Bold" if _UBUNTU_AVAILABLE else "Helvetica-Bold"
FONT_BOLD_ITALIC = "Ubuntu-BoldItalic" if _UBUNTU_AVAILABLE else "Helvetica-BoldOblique"


class CvPdfGenerator:
    """
    Générateur de PDF pour les CV (format ATS avec style : marges 1 cm, couleurs bleu marine / violet, police Ubuntu).
    """
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.cv_dir = os.path.join(output_dir, "cvs")
        self.lm_dir = os.path.join(output_dir, "lms")
        for d in [self.cv_dir, self.lm_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

    def generate(self, filename: str, cv_data: dict) -> str:
        """
        Génère un fichier PDF à partir des données du CV. Marges 1 cm, interligne simple (0 avant, 3 après),
        titre en gras italique, intitulés en gras (couleur primaire), noms de sociétés en gras + couleur secondaire.
        """
        filepath = os.path.join(self.cv_dir, filename)
        try:
            doc = SimpleDocTemplate(
                filepath,
                pagesize=letter,
                leftMargin=MARGIN_PT,
                rightMargin=MARGIN_PT,
                topMargin=MARGIN_PT,
                bottomMargin=MARGIN_PT,
            )
            styles = getSampleStyleSheet()

            # Interligne simple : 0 avant, 3 après ; leading ≈ 1,2 × fontSize
            normal_style = ParagraphStyle(
                "CVNormal",
                parent=styles["Normal"],
                fontName=FONT_FAMILY,
                fontSize=11,
                leading=13.2,
                spaceBefore=0,
                spaceAfter=3,
            )

            # Intitulés de section : gras, couleur primaire (bleu marine)
            heading_style = ParagraphStyle(
                "CVHeading",
                parent=styles["Normal"],
                fontName=FONT_BOLD,
                fontSize=12,
                leading=14,
                spaceBefore=12,
                spaceAfter=3,
                textColor=HexColor(COLOR_PRIMARY_HEX),
            )

            # Titre (nom) : gras italique
            title_style = ParagraphStyle(
                "CVTitle",
                parent=styles["Title"],
                fontName=FONT_BOLD_ITALIC,
                fontSize=14,
                alignment=0,
                spaceAfter=2,
                textColor=HexColor(COLOR_PRIMARY_HEX),
            )

            story = []

            # 1. CARTOUCHE
            story.append(Paragraph(f"<b><i>{cv_data.get('nom', 'LUCAS TYMEN').upper()}</i></b>", title_style))
            story.append(Paragraph(cv_data.get('adresse', ''), normal_style))
            story.append(Paragraph(cv_data.get('telephone', ''), normal_style))
            story.append(Paragraph(cv_data.get('email', ''), normal_style))
            story.append(Paragraph(cv_data.get('linkedin', ''), normal_style))
            story.append(Spacer(1, 12))

            # 2. TITRE DE POSTE (intitulé en gras, couleur primaire)
            titre_poste = (cv_data.get('titre_poste') or '').upper()
            story.append(Paragraph(f'<font color="{COLOR_PRIMARY_HEX}"><b>{titre_poste}</b></font>', heading_style))
            story.append(Spacer(1, 12))

            # 3. PROFIL
            story.append(Paragraph(f'<font color="{COLOR_PRIMARY_HEX}"><b>Profil</b></font>', heading_style))
            story.append(Paragraph(cv_data.get('profil', ''), normal_style))

            # 4. COMPÉTENCES
            story.append(Paragraph(f'<font color="{COLOR_PRIMARY_HEX}"><b>Compétences</b></font>', heading_style))
            for cat, comps in cv_data.get('competences_ats', {}).items():
                story.append(Paragraph(f"<b>{cat}</b> : {', '.join(comps)}", normal_style))

            # 5. EXPÉRIENCES — intitulés en gras ; noms des sociétés en gras + couleur secondaire
            story.append(Paragraph(f'<font color="{COLOR_PRIMARY_HEX}"><b>Expériences</b></font>', heading_style))
            for exp in cv_data.get('experiences', []):
                role = exp.get('role') or ''
                entite = exp.get('entite') or ''
                periode = exp.get('periode') or ''
                header = (
                    f'<b>{role}</b> – '
                    f'<font color="{COLOR_SECONDARY_HEX}"><b>{entite}</b></font>'
                    f' ({periode})'
                )
                story.append(Paragraph(header, normal_style))
                for bullet in exp.get('bullets', []):
                    story.append(Paragraph(bullet, normal_style))
                story.append(Spacer(1, 6))

            # 6. FORMATION — noms d'établissements en gras + couleur secondaire
            story.append(Paragraph(f'<font color="{COLOR_PRIMARY_HEX}"><b>Formation</b></font>', heading_style))
            for edu in cv_data.get('formation', []):
                ecole = edu.get('ecole') or edu.get('etablissement', '')
                diplome = edu.get('diplome') or edu.get('intitule') or edu.get('niveau', '')
                annee = edu.get('annee', '')
                line = f'<font color="{COLOR_SECONDARY_HEX}"><b>{ecole}</b></font> – {diplome} ({annee})'
                story.append(Paragraph(line, normal_style))

            doc.build(story)
            return filepath
        except Exception as e:
            print(f"Erreur lors de la génération du CV PDF : {e}")
            return None

    def generate_lm(self, filename: str, lm_text: str) -> str:
        """
        Génère un fichier PDF pour la lettre de motivation. Marges 1 cm, interligne simple (0 avant, 3 après), police Ubuntu si dispo.
        """
        filepath = os.path.join(self.lm_dir, filename)
        try:
            doc = SimpleDocTemplate(
                filepath,
                pagesize=letter,
                leftMargin=MARGIN_PT,
                rightMargin=MARGIN_PT,
                topMargin=MARGIN_PT,
                bottomMargin=MARGIN_PT,
            )
            styles = getSampleStyleSheet()
            normal_style = ParagraphStyle(
                "LMNormal",
                parent=styles["Normal"],
                fontName=FONT_FAMILY,
                fontSize=11,
                leading=13.2,
                spaceBefore=0,
                spaceAfter=3,
            )
            story = []
            for part in lm_text.split("\n\n"):
                story.append(Paragraph(part.replace("\n", "<br/>"), normal_style))
                story.append(Spacer(1, 12))
            doc.build(story)
            return filepath
        except Exception as e:
            print(f"Erreur lors de la génération de la LM PDF : {e}")
            return None
