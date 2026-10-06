# Pop-up de fin de veille : notification Windows native (aucun module à installer).
# Appelé par lancer_veille.bat avec le code de retour de la veille.
# Usage manuel : powershell -ExecutionPolicy Bypass -File scripts\notifier.ps1 0
param([int]$CodeRetour = 0)

$racine = Split-Path -Parent $PSScriptRoot
$cheminResume = Join-Path $racine "data\processed\resume.json"
$cheminJournal = Join-Path $racine "data\veille.log"

function Echapper([string]$texte) { [Security.SecurityElement]::Escape($texte) }
function Uri([string]$chemin) { "file:///" + ($chemin -replace '\\', '/') }

if ($CodeRetour -ne 0 -or -not (Test-Path $cheminResume)) {
    $titre = "Veille alternance : échec"
    $lignes = @("La veille ne s'est pas terminée correctement.", "Consulte le journal pour le détail.")
    $cible = $cheminJournal
    $bouton = "Ouvrir le journal"
} else {
    $resume = Get-Content $cheminResume -Raw -Encoding UTF8 | ConvertFrom-Json
    $date = ([datetime]::ParseExact($resume.jour, "yyyy-MM-dd", $null)).ToString("dd/MM")
    $titre = "Veille alternance du $date"
    $pluriel = if ($resume.nb_nouvelles -gt 1) { "s" } else { "" }
    $chiffres = "$($resume.nb_nouvelles) nouvelle$pluriel offre$pluriel · $($resume.nb_offres) actives · $($resume.nb_recruteurs) entreprises"
    if ($resume.nb_nouvelles -eq 0) {
        $detail = "Rien de nouveau aujourd'hui."
    } else {
        $detail = ($resume.nouvelles | Select-Object -First 3 | ForEach-Object {
            $entreprise = if ($_.entreprise) { " — $($_.entreprise)" } else { "" }
            "• $($_.titre)$entreprise ($($_.departement))"
        }) -join "`n"
        if ($resume.nb_nouvelles -gt 3) { $detail += "`n… et $($resume.nb_nouvelles - 3) autre(s)" }
    }
    $lignes = @($chiffres, $detail)
    $cible = $resume.rapport
    $bouton = "Ouvrir le rapport"
}

$textes = ($lignes | ForEach-Object { "<text>$(Echapper $_)</text>" }) -join ""
$lien = Echapper (Uri $cible)
$xml = @"
<toast activationType="protocol" launch="$lien" duration="long">
  <visual><binding template="ToastGeneric"><text>$(Echapper $titre)</text>$textes</binding></visual>
  <actions><action content="$(Echapper $bouton)" activationType="protocol" arguments="$lien"/></actions>
</toast>
"@

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$document = New-Object Windows.Data.Xml.Dom.XmlDocument
$document.LoadXml($xml)
$notification = New-Object Windows.UI.Notifications.ToastNotification $document
# Identifiant d'application de PowerShell : la notification apparaît sous « Windows PowerShell »
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($notification)
