package de.rennschmiede.aerostudio;

import com.ptc.cipjava.jxthrowable;
import com.ptc.pfc.pfcCommand.DefaultUICommandActionListener;
import com.ptc.pfc.pfcCommand.UICommand;
import com.ptc.pfc.pfcSession.CreoCompatibility;
import com.ptc.pfc.pfcSession.Session;
import com.ptc.pfc.pfcSession.pfcSession;

/**
 * Einstiegspunkt des Aero-Studio-Plugins fuer Creo Parametric 8.
 *
 * Registriert zwei Befehle im Menue "Werkzeuge":
 *
 *   IBL importieren    - Datei waehlen und als Bezugskurve einfuegen
 *   IBL aktualisieren  - dieselbe Datei erneut einlesen, ohne Dialog
 *
 * Der zweite Befehl ist der eigentliche Zweck des Plugins. Creo liest eine
 * importierte Bezugskurve beim Regenerieren nicht neu ein, und "Definition
 * bearbeiten" oeffnet den Import DataDoctor statt des Dateidialogs. Ueber die
 * API geht es dagegen sauber: WFeature.RedefineImportFeature() liest die Datei
 * in das BESTEHENDE Feature neu ein. Damit bleiben alle nachgelagerten
 * Features - Boundary Blend, Verdicken, Verrundungen - erhalten und
 * regenerieren einfach mit.
 *
 * Der Klassenname muss in der protk.dat unter java_app_class stehen.
 */
public class AeroStudioPlugin {

    private static final String NAME = "Aero Studio";

    /** Von Creo beim Starten der Anwendung aufgerufen. */
    public static void start() {
        melde("gestartet");
        try {
            Session sitzung = pfcSession.GetCurrentSessionWithCompatibility(
                    CreoCompatibility.C4Compatible);

            UICommand importieren = sitzung.UICreateCommand(
                    "AeroStudio.ImportIBL", new ImportListener());
            sitzung.UIAddButton(importieren, "Utilities", null,
                    "-Aero Studio: IBL importieren",
                    "IBL-Datei waehlen und als Bezugskurve einfuegen",
                    "msg_aerostudio.txt");

            UICommand aktualisieren = sitzung.UICreateCommand(
                    "AeroStudio.UpdateIBL", new AktualisierenListener());
            sitzung.UIAddButton(aktualisieren, "Utilities", null,
                    "-Aero Studio: IBL aktualisieren",
                    "Zuletzt importierte IBL-Datei erneut einlesen",
                    "msg_aerostudio.txt");

            melde("Befehle registriert");
        } catch (jxthrowable x) {
            melde("Registrierung fehlgeschlagen: " + x);
            x.printStackTrace();
        }
    }

    /** Von Creo beim Beenden der Anwendung aufgerufen. */
    public static void stop() {
        melde("beendet");
    }

    static void melde(String text) {
        System.out.println("[" + NAME + "] " + text);
    }

    // ------------------------------------------------------------------

    static class ImportListener extends DefaultUICommandActionListener {
        @Override
        public void OnCommand() {
            try {
                IblImport.importierenMitDialog(aktuelleSitzung());
            } catch (Exception x) {
                IblImport.zeigeFehler(x);
            }
        }
    }

    static class AktualisierenListener extends DefaultUICommandActionListener {
        @Override
        public void OnCommand() {
            try {
                IblImport.aktualisieren(aktuelleSitzung());
            } catch (Exception x) {
                IblImport.zeigeFehler(x);
            }
        }
    }

    static Session aktuelleSitzung() throws jxthrowable {
        return pfcSession.GetCurrentSessionWithCompatibility(
                CreoCompatibility.C4Compatible);
    }
}
