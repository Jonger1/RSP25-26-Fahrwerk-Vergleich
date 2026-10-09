package de.rennschmiede.aerostudio;

import java.io.File;

import javax.swing.JFileChooser;
import javax.swing.JOptionPane;
import javax.swing.filechooser.FileNameExtensionFilter;

import com.ptc.cipjava.jxthrowable;
import com.ptc.pfc.pfcFeature.Feature;
import com.ptc.pfc.pfcGeometry.CoordSystem;
import com.ptc.pfc.pfcModel.Model;
import com.ptc.pfc.pfcModelItem.ModelItem;
import com.ptc.pfc.pfcModelItem.ModelItemType;
import com.ptc.pfc.pfcModelItem.ModelItems;
import com.ptc.pfc.pfcModelItem.ParamValue;
import com.ptc.pfc.pfcModelItem.Parameter;
import com.ptc.pfc.pfcModelItem.pfcModelItem;
import com.ptc.pfc.pfcSession.Session;
import com.ptc.pfc.pfcSolid.Solid;
import com.ptc.wfc.wfcFeature.ImportRedefByDataSource;
import com.ptc.wfc.wfcFeature.WFeature;
import com.ptc.wfc.wfcFeature.wfcFeature;
import com.ptc.wfc.wfcModel.IntfIBL;
import com.ptc.wfc.wfcModel.wfcModel;
import com.ptc.wfc.wfcSolid.WSolid;

/**
 * Import und Aktualisierung einer IBL-Kurve.
 *
 * Zustand wird im Modell selbst gehalten, nicht im Plugin - damit ueberlebt er
 * das Schliessen von Creo und wandert mit dem Teil mit:
 *
 *   AERO_IBL_PFAD     Pfad der zuletzt importierten Datei
 *   AERO_IBL_FEAT_ID  Feature-Nummer der erzeugten Bezugskurve
 *
 * Der Ablauf ist bewusst idempotent: "aktualisieren" laesst sich beliebig oft
 * ausloesen. Existiert das Feature nicht mehr, wird neu importiert statt eine
 * Fehlermeldung zu werfen.
 */
final class IblImport {

    private static final String P_PFAD = "AERO_IBL_PFAD";
    private static final String P_FEAT = "AERO_IBL_FEAT_ID";

    /** Bevorzugtes Koordinatensystem; fehlt es, wird das erste im Modell genommen. */
    private static final String KS_NAME = "CS_AERO";

    private IblImport() {
    }

    // ------------------------------------------------------------------

    static void importierenMitDialog(Session sitzung) throws jxthrowable {
        Solid teil = aktuellesTeil(sitzung);
        if (teil == null) {
            hinweis("Kein Teil geoeffnet.\n\n"
                    + "Aero Studio importiert in das gerade aktive Teil. "
                    + "Bitte zuerst ein Teil oeffnen oder neu anlegen.");
            return;
        }

        File vorgabe = null;
        String letzter = leseText(teil, P_PFAD);
        if (letzter != null && !letzter.isEmpty()) {
            File f = new File(letzter);
            vorgabe = f.getParentFile();
        }

        JFileChooser dialog = new JFileChooser(vorgabe);
        dialog.setDialogTitle("Aero Studio: IBL-Datei waehlen");
        dialog.setFileFilter(new FileNameExtensionFilter("IBL-Kurvendateien (*.ibl)", "ibl"));
        if (dialog.showOpenDialog(null) != JFileChooser.APPROVE_OPTION) {
            return;
        }

        File datei = dialog.getSelectedFile();
        Feature feature = importiere(teil, datei.getAbsolutePath());

        schreibeText(teil, P_PFAD, datei.getAbsolutePath());
        schreibeZahl(teil, P_FEAT, feature.GetId());

        AeroStudioPlugin.melde("importiert: " + datei.getAbsolutePath()
                + " als Feature " + feature.GetId());
        hinweis("Importiert:\n" + datei.getName()
                + "\n\nFeature-Nummer " + feature.GetId()
                + "\n\nAenderungen an der Datei koennen ab jetzt ueber\n"
                + "\"Aero Studio: IBL aktualisieren\" eingelesen werden.");
    }

    static void aktualisieren(Session sitzung) throws jxthrowable {
        Solid teil = aktuellesTeil(sitzung);
        if (teil == null) {
            hinweis("Kein Teil geoeffnet.");
            return;
        }

        String pfad = leseText(teil, P_PFAD);
        if (pfad == null || pfad.isEmpty()) {
            hinweis("In diesem Teil wurde noch keine IBL-Datei importiert.\n\n"
                    + "Bitte zuerst \"Aero Studio: IBL importieren\" verwenden.");
            return;
        }
        if (!new File(pfad).isFile()) {
            hinweis("Die Datei ist nicht mehr auffindbar:\n\n" + pfad
                    + "\n\nWurde sie verschoben oder umbenannt? "
                    + "Dann bitte neu importieren.");
            return;
        }

        Integer id = leseZahl(teil, P_FEAT);
        WFeature feature = (id == null) ? null : sucheFeature(teil, id);

        if (feature == null) {
            // Feature geloescht oder Modell frisch - dann eben neu anlegen.
            Feature neu = importiere(teil, pfad);
            schreibeZahl(teil, P_FEAT, neu.GetId());
            AeroStudioPlugin.melde("Feature fehlte, neu importiert: " + pfad);
            hinweis("Die frueher importierte Kurve war nicht mehr vorhanden.\n"
                    + "Die Datei wurde neu importiert.");
            return;
        }

        IntfIBL quelle = wfcModel.IntfIBL_Create(pfad);
        ImportRedefByDataSource anweisung = wfcFeature.ImportRedefByDataSource_Create(quelle);
        feature.RedefineImportFeature(anweisung);

        AeroStudioPlugin.melde("aktualisiert: " + pfad);
        hinweis("Aktualisiert:\n" + new File(pfad).getName());
    }

    // ------------------------------------------------------------------

    /**
     * Legt das Import-Feature an.
     *
     * Der letzte Parameter von ImportAsFeat ist entscheidend: true bedeutet
     * "als Bezugskurve importieren" - genau das, was der Dialog unter
     * Importtyp "Kurve" macht.
     */
    private static Feature importiere(Solid teil, String pfad) throws jxthrowable {
        IntfIBL quelle = wfcModel.IntfIBL_Create(pfad);
        CoordSystem ks = sucheKoordinatensystem(teil);
        WSolid wteil = (WSolid) teil;
        return wteil.ImportAsFeat(quelle, ks, null, null, Boolean.TRUE);
    }

    /**
     * Sucht CS_AERO, sonst das erste Koordinatensystem, sonst null.
     *
     * Seit der Exporter die Koordinaten bereits in das System der Creo-Vorlage
     * dreht, genuegt das Standard-Koordinatensystem. CS_AERO wird nur noch
     * bevorzugt, falls jemand eines angelegt hat.
     */
    private static CoordSystem sucheKoordinatensystem(Solid teil) throws jxthrowable {
        ModelItem benannt = teil.GetItemByName(ModelItemType.ITEM_COORD_SYS, KS_NAME);
        if (benannt instanceof CoordSystem) {
            return (CoordSystem) benannt;
        }
        ModelItems alle = teil.ListItems(ModelItemType.ITEM_COORD_SYS);
        if (alle != null && alle.getarraysize() > 0) {
            ModelItem erstes = alle.get(0);
            if (erstes instanceof CoordSystem) {
                return (CoordSystem) erstes;
            }
        }
        return null;
    }

    private static WFeature sucheFeature(Solid teil, int id) {
        try {
            ModelItem item = teil.GetItemById(ModelItemType.ITEM_FEATURE, id);
            if (item instanceof WFeature) {
                return (WFeature) item;
            }
        } catch (jxthrowable ignoriert) {
            // Feature existiert nicht mehr - der Aufrufer legt dann neu an.
        }
        return null;
    }

    // ---------------------------------------------------- Modellparameter

    private static String leseText(Model modell, String name) {
        try {
            Parameter p = modell.GetParam(name);
            return (p == null) ? null : p.GetValue().GetStringValue();
        } catch (jxthrowable x) {
            return null;
        }
    }

    private static Integer leseZahl(Model modell, String name) {
        try {
            Parameter p = modell.GetParam(name);
            return (p == null) ? null : Integer.valueOf(p.GetValue().GetIntValue());
        } catch (jxthrowable x) {
            return null;
        }
    }

    private static void schreibeText(Model modell, String name, String wert) throws jxthrowable {
        ParamValue v = pfcModelItem.CreateStringParamValue(wert);
        Parameter p = modell.GetParam(name);
        if (p == null) {
            modell.CreateParam(name, v);
        } else {
            p.SetValue(v);
        }
    }

    private static void schreibeZahl(Model modell, String name, int wert) throws jxthrowable {
        ParamValue v = pfcModelItem.CreateIntParamValue(wert);
        Parameter p = modell.GetParam(name);
        if (p == null) {
            modell.CreateParam(name, v);
        } else {
            p.SetValue(v);
        }
    }

    // ------------------------------------------------------------- Hilfen

    private static Solid aktuellesTeil(Session sitzung) throws jxthrowable {
        Model modell = sitzung.GetCurrentModel();
        return (modell instanceof Solid) ? (Solid) modell : null;
    }

    private static void hinweis(String text) {
        JOptionPane.showMessageDialog(null, text, "Aero Studio",
                JOptionPane.INFORMATION_MESSAGE);
    }

    static void zeigeFehler(Exception x) {
        AeroStudioPlugin.melde("Fehler: " + x);
        x.printStackTrace();
        JOptionPane.showMessageDialog(null,
                "Der Vorgang ist fehlgeschlagen.\n\n" + x
                        + "\n\nEinzelheiten stehen im Creo-Startfenster.",
                "Aero Studio", JOptionPane.ERROR_MESSAGE);
    }
}
