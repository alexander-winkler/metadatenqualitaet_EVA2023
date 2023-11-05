import requests
from lxml import etree
import re
from datetime import datetime
import re
from statistics import mean
import iso8601


def resultNumberFromProvider(providerID):
    url = f"https://api.deutsche-digitale-bibliothek.de/search?oauth_consumer_key=pBcqMKqGh6fY12mJlXvTcQu2ZQNMnLtRShF1DtQPbDHqkO8AFrl1657532358832&facet=provider_id&provider_id={providerID}&rows=0"
    res = requests.get(url).json()
    numberOfResults = res.get('numberOfResults')
    return numberOfResults

def itemsFromProvider(providerID, offset, rows) -> list:
    url = f"https://api.deutsche-digitale-bibliothek.de/search?oauth_consumer_key=pBcqMKqGh6fY12mJlXvTcQu2ZQNMnLtRShF1DtQPbDHqkO8AFrl1657532358832&facet=provider_id&provider_id={providerID}&offset={offset}&rows={rows}&sort=random_805964166784363941"
    res = requests.get(url)
    res = res.json()
    results = res.get('results')[0].get('docs')
    results = [_.get('id') for _ in results]
    return results

def iterationProvider(providerID, step = 1000):
    objectList = []
    n = resultNumberFromProvider(providerID)
    for i in range(0,n,step):
        objectList.extend(
            itemsFromProvider(providerID,i,step)
        )
    return objectList

def numberFromSite(museumsID) -> int:
    museumsListe = f"https://www.deutsche-digitale-bibliothek.de/searchresults?query=&offset=0&rows=1&facetValues%5B%5D=provider_id%3D{museumsID}&sort=ALPHA_ASC"
    res = requests.get(museumsListe)
    tree = etree.HTML(res.content)
    try:
        total_results_element = tree.find(".//span[@class='total-results']")
        total_results = int(total_results_element.text.replace('.',''))
        return total_results
    except:
        return 0

def ObjectFromSite(museumsID, offset = 0, rows = 1000) -> list:
    museumsListe = f"https://www.deutsche-digitale-bibliothek.de/searchresults?query=&offset={offset}&rows={rows}&facetValues%5B%5D=provider_id%3D{museumsID}&sort=ALPHA_ASC"
    res = requests.get(museumsListe)
    tree = etree.HTML(res.content)

    # Extract the text content of the span element
    links = tree.xpath("//h3[@class='title title-list']/a[@class='persist h4-ddb']/@href")
    links = [re.search(r'/item/(\w+)?',l).group(1) for l in links]
    return links

def iterSite(museumsID, rows = 1000):
    results = []
    n = numberFromSite(museumsID)
    if n:
        for i in range(0,n, rows):
            results.extend(ObjectFromSite(museumsID, offset = i))
        return results
    else:
        return []


# +
def formatGuesser(tree):
    """Simple Funktion, die anhand der
    verwendeten Namespace-Präfixe auf das
    Format schließt. Wesentliche Funktion ist,
    LIDO-Dateien als solche zu erkennen."""
    NSMAP = tree.getroot().nsmap.keys()
    if "lido" in NSMAP:
        f = "lido"
    elif "mets" in NSMAP:
        f = "mets"
    else:
        f = "unknown"
        
    return f

lidoSchema = requests.get("http://lido-schema.org/schema/v1.1/lido-v1.1.xsd")
xmlschema_doc = etree.fromstring(lidoSchema.content)
xmlschema = etree.XMLSchema(xmlschema_doc)

def LIDOvalidator(tree, xmlschema):
    """Gibt True zurück, wenn Etree-Objekt
    schemavalides LIDO ist."""
    if xmlschema.validate(tree) == True:
        return 1
    else:
        return 0
    
def parseLicense(license):
    cc = re.match(r'\S+//creativecommons.org/(?:licenses/)?([^/]+)/(\d\.\d)',license)
    pd = re.match(r'\S+//creativecommons.org/publicdomain/mark\S+',license)
    cc0 = re.match(r'\S+//creativecommons.org/publicdomain/zero/1.0',license)
    rvfz = re.match(r'\S+www.deutsche-digitale-bibliothek.de/\S+/rv-fz',license)
    rvez = re.match(r'\S+www.deutsche-digitale-bibliothek.de/\S+/rv-ez',license)
    rrfa = re.match(r'\S+www.europeana.eu/\S+/rr-f',license)
    if cc:
        return f"CC {cc.group(1)} {cc.group(2)}".upper()
    elif pd:
        return "PD"
    elif cc0:
        return "CC0"
    elif rvfz:
        return "RVFZ"
    elif rvez:
        return "RVEZ"
    elif rrfa:
        return "RRFA"
    else:
        return license

# Lizenzen vov strikt zu offen
licenseOrder = ["RRFA","RVEZ","RVFZ","CC ", "CC0", "PD"]

    

def dateparser(datestring):
    now = datetime.now()
    date = re.search(r'\d{4}\W\d{2}\W\d{2}', datestring)
    if date:
        date_str = date.group()
        date_str = date_str.replace('.','-')
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        diff = now-date_obj
        return diff.days
    else:
        return None
    
class LIDO:
    def __init__(self,tree):
        self.tree = tree
        self.NSMAP = tree.getroot().nsmap
        self.RecID = tree.find('.//lido:lidoRecID', self.NSMAP).text
        
        # Actor Elemente
        self.actors = list()
        for i in self.tree.findall('//lido:actor', self.NSMAP):
            self.actors.append({
            'actorContext' : etree.QName(i.getparent()).localname,
            'actorIDs' : [_.text for _ in i.findall('./lido:actorID', self.NSMAP)],
            'actorIDsSource' : [_.attrib.get('{http://www.lido-schema.org}source') for _ in i.findall('./lido:actorID', self.NSMAP)],
            'actorNameString' : i.find('./lido:nameActorSet/lido:appellationValue', self.NSMAP).text
        })
        self.actorUris = []
        for _ in self.actors:
            self.actorUris.extend(_.get('actorIDs'))

        # Ortsinformationen
        # Problem: Ignoriert z.B. Orte innerhalb <lido:partOfPlace>-Elemente
        self.places = list()
        for i in self.tree.findall('//lido:place', self.NSMAP):
            try:
                self.placeNameString = i.find('./lido:namePlaceSet/lido:appellationValue', self.NSMAP).text
            except:
                self.placeNameString = ""
            
            self.places.append({
                'placeContext' : etree.QName(i.getparent()).localname,
                'placeIDs' : [_.text for _ in i.findall('./lido:placeID', self.NSMAP)],
                'placeNameString' : self.placeNameString
        })
        self.placeUris = []
        for _ in self.places:
            self.placeUris.extend(_.get('placeIDs'))

        # Schlagworte
        self.subjects = list()
        for i in self.tree.findall('//lido:subjectConcept', self.NSMAP):
            try:
                self.subjectString = i.find('./lido:term', self.NSMAP).text
            except:
                self.subjectString = ""
        
            self.subjects.append({
                'subjectContext' : etree.QName(i.getparent()).localname,
                'subjectIDs' : [_.text for _ in i.findall('./lido:conceptID', self.NSMAP)],
                'subjectString' : self.subjectString
            })
        self.subjectUris = []
        for _ in self.subjects:
            self.subjectUris.extend(_.get('subjectIDs'))
            
        # Objekttyp
        self.objectWorkTypes = list()
        for i in self.tree.findall('//lido:objectWorkType', self.NSMAP):
            try:
                self.objectWorkTypeString = i.find('./lido:term', self.NSMAP).text # wählt nur eine Sprachvariante
            except:
                self.objectWorkTypeString = ""

            self.objectWorkTypes.append({
                'objectWorkTypeIDs' : [_.text for _ in i.findall('./lido:conceptID', self.NSMAP)],
                'objectWorkTypeString' : self.objectWorkTypeString
                })
        self.objectWorkTypeUris = []
        for _ in self.objectWorkTypes:
            self.objectWorkTypeUris.extend(_.get('objectWorkTypeIDs'))
            
        # Record Lizenz
        self.recordRights = list()
        for i in self.tree.findall('//lido:recordRights/lido:rightsType', self.NSMAP):
            try:
                self.recordRightString = i.find('./lido:term', self.NSMAP).text
            except:
                self.recordRightString = ""
                
                
            self.recordRights.append({
                'conceptIDs' : [_.text for _ in i.findall('./lido:conceptID', self.NSMAP)],
                'conceptTerm' : self.recordRightString
            })
        
        # einzelner normierter Lizenzwert
        lizenzangaben = []
        self.license = None
        for r in self.recordRights:
            for conceptID in r.get('conceptIDs'):
                lizenzangaben.append(parseLicense(conceptID))
        # Iteration durch die Lizenzliste (von restriktiv zu offen),
        # wird bei restriktivster Lizenz unterbrochen
        for lO in licenseOrder:
            for lizenz in lizenzangaben:
                if lizenz.startswith(lO):
                    self.license = lizenz
                    break
        
        # Record Datum
        self.recordMetadataDate = list()
        for i in self.tree.findall('//lido:recordInfoSet/lido:recordMetadataDate', self.NSMAP):
            self.recordMetadataDate.append(i.text)
            
        # Alter
        if len(self.recordMetadataDate) > 0:
            self.age = min([dateparser(d) for d in self.recordMetadataDate])
        else:
            self.age = None
    
        ##############
        ## Coverage ##
        ##############
        
        # Actor
        self.numActors = len(self.actors)
        self.numActorIDs = len([a for a in self.actors if len(a.get('actorIDs')) > 0])
        if self.numActors > 0 :
            self.actorCoverage = self.numActorIDs/self.numActors
        else:
            self.actorCoverage = None   

        # Orte
        self.numPlaces = len(self.places)
        self.numPlaceIDs = len([place for place in self.places if len(place.get('placeIDs')) > 0])
        if self.numPlaces > 0 :
            self.placeCoverage = self.numPlaceIDs/self.numPlaces
        else:
            self.placeCoverage = None
        
        # Schlagwörter
        self.numSubjects = len(self.subjects)
        self.numSubjectIDs = len([subject for subject in self.subjects if len(subject.get('subjectIDs')) > 0])
        if self.numSubjects > 0 :
            self.subjectCoverage = self.numSubjectIDs/self.numSubjects
        else:
            self.subjectCoverage = None
            
        # Objekttyp
        self.numObjectWorkTypes = len(self.objectWorkTypes)
        self.numObjectWorkTypeIDs = len([owt for owt in self.objectWorkTypes if len(owt.get('objectWorkTypeIDs')) > 0])
        if self.numObjectWorkTypes > 0 :
            self.objectWorkTypeCoverage = self.numObjectWorkTypeIDs/self.numObjectWorkTypes
        else:
            self.objectWorkTypeCoverage = None

        # Kumulativ
        self.cumulativeCoverage = [_ for _ in [self.actorCoverage, self.placeCoverage, self.subjectCoverage, self.objectWorkTypeCoverage] if _ is not None]
        if len(self.cumulativeCoverage) > 0:
            self.cumulativeCoverage = mean(self.cumulativeCoverage)
        else:
            self.cumulativeCoverage = None
            
        
        #############################
        ### Standardisierte Werte ###
        #############################
        
               
        # Datumsstandardisierung
        self.eventDates = tree.findall('.//lido:eventDate', self.NSMAP)
        if len(self.eventDates) > 0:
            self.eventCoverage = []
            self.displayDates = []
            for e in self.eventDates:
                self.displayDates.extend([d.text for d in e.findall('./lido:displayDate', self.NSMAP)])
                try:
                    earliest = e.find('./lido:date/lido:earliestDate', self.NSMAP).text
                except:
                    earliest = None
                try:
                    latest = e.find('./lido:date/lido:latestDate', self.NSMAP).text
                except:
                    latest = None

                if earliest is not None and latest is not None:
                    earliest = earliest.removeprefix('-').strip().zfill(4)
                    latest = latest.removeprefix('-').strip().zfill(4)

                    if iso8601.is_iso8601(earliest) and iso8601.is_iso8601(latest):
                        self.eventCoverage.append(1)
                    else:
                        self.eventCoverage.append(0)
                else:
                    self.eventCoverage.append(0)

            if len(self.eventCoverage) > 0:
                self.dateCoverage = mean(self.eventCoverage)
            else:
                self.dateCoverage = None
        else:
            self.dateCoverage = None
                
        # Standardisierungsgrad bei Maßangaben
        self.measurementSets = tree.findall('.//lido:objectMeasurements/lido:measurementsSet', self.NSMAP)
        self.measurements = []
        for mS in self.measurementSets:
            try:
                mS.find('lido:measurementType', self.NSMAP).text
                mS.find('lido:measurementUnit', self.NSMAP).text
                float(mS.find('lido:measurementValue', self.NSMAP).text.replace(',','.'))
                self.measurements.append(1)
            except:
                self.measurements.append(0)
                
        if len(self.measurements) > 0:
            self.measureCoverage = mean(self.measurements)
        else:
            self.measureCoverage = None
