# janaf.py

# This module gets thermodynamic datat from the JANAF database.
# Files are downloaded from the NIST servers as needed and then cached locally.
#
# Zack Gainsforth
#
# Funding by NASA

from __future__ import division
from __future__ import print_function

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import os

try:
    # Python 3
    import urllib.request as urllib2
except ImportError:
    # Python 2
    import urllib2

try:
    # Python 2
    from StringIO import StringIO
except ImportError:
    # Python 3
    from io import StringIO


# Universal gas constant R
R = 8.314472

class JanafPhase(object):
    """
    Class which is created by Janafdb for a specific phase.

    It reads in the JANAF data file and produces functions which interpolate the thermodynamic
    constants.

    >>> db = Janafdb()
    >>> p = db.getphasedata(formula='O2Ti', name='Rutile', phase='cr')
    >>> print(p.cp([500, 550, 1800]))
    [ 67.203  68.567  78.283]
    >>> print(p.S([500, 550, 1800]))
    [  82.201    88.4565  176.876 ]
    >>> print(p.gef([500, 550, 1800]))
    [  57.077   59.704  115.753]
    >>> print(p.hef([500, 550, 1800]))
    [  12.562    15.9955  110.022 ]
    >>> print(p.DeltaH([500, 550, 1800]))
    [-943.67   -943.2295 -936.679 ]
    >>> print(p.DeltaG([500, 550, 1800]))
    [-852.157  -843.0465 -621.013 ]
    >>> print(p.logKf([500, 550, 1800]))
    [ 89.024   80.8125  18.021 ]
    >>> print(p.cp(50000))
    Traceback (most recent call last):
        ...
    ValueError: A value in x_new is above the interpolation range.
    """
    def __init__(self, rawdata_text):
        # Store the raw data text file from NIST.
        self.rawdata_text = rawdata_text

        # Read the text file into a DataFrame.
        data = pd.read_csv(StringIO(self.rawdata_text), skiprows=2, header=None, delimiter='[\t\s]*', engine='python')
        data.columns = ['T', 'Cp', 'S', '[G-H(Tr)]/T', 'H-H(Tr)', 'Delta_fH', 'Delta_fG', 'log(Kf)']
        self.rawdata = data

        # Sometimes the JANAF files have funky stuff written in them.  (Old school text format...)
        # Clean it up.
        for c in data.columns:
            # We only need to polish up columns that aren't floating point numbers.
            if np.issubdtype(data.dtypes[c], np.floating):
                continue
            # Change INFINITE to inf
            data.loc[data[c] == 'INFINITE', c]
            # Anything else becomes a nan.
            # Convert to floats.
            data[c] = pd.to_numeric(data[c], errors='coerce')

        # Now make interpolatable functions for each of these.
        self.cp = interp1d(self.rawdata['T'], self.rawdata['Cp'])
        self.S = interp1d(self.rawdata['T'], self.rawdata['S'])
        self.gef = interp1d(self.rawdata['T'], self.rawdata['[G-H(Tr)]/T'])
        self.hef = interp1d(self.rawdata['T'], self.rawdata['H-H(Tr)'])
        self.DeltaH = interp1d(self.rawdata['T'], self.rawdata['Delta_fH'])
        self.DeltaG = interp1d(self.rawdata['T'], self.rawdata['Delta_fG'])
        self.logKf = interp1d(self.rawdata['T'], self.rawdata['log(Kf)'])

        # TODO Deal well with crystal<->liquid transitions which have a below and above value for Cp, S, etc.

class Janafdb(object):

    """
    Class that reads the NIST JANAF tables for thermodynamic data.

    Data is initially read from the web servers, and then cached.
    """

    def __init__(self):
        """
        We have an index file which can be used to build the url for all phases on the NIST site.
        """

        # Read the index file which tells us the filenames for all the phases in the JANAF database.
        self.db = pd.read_csv("thermochem/JANAF_index.txt", delimiter='|')
        # Name the columns and trim whitespace off the text fields.
        self.db.columns = ['formula', 'name', 'phase', 'filename']
        self.db["formula"] = self.db["formula"].map(str.strip)
        self.db["name"] = self.db["name"].map(str.strip)
        self.db["phase"] = self.db["phase"].map(str.strip)
        self.db["filename"] = self.db["filename"].map(str.strip)

        # Make sure that the directory for cached JANAF files exists.
        self.JANAF_cachedir = os.path.join('.', 'thermochem', 'JANAF_Cache')
        if not os.path.exists(self.JANAF_cachedir):
            os.mkdir(self.JANAF_cachedir)

    def search(self, searchstr):
        """
        List all the species containing a string. Helpful for
        interactive use of the database.
        returns a pandas dataframe containing valid phases.

        >>> db = Janafdb()
        >>> s = db.search('Rb-')
        >>> print(s)
             formula           name phase filename
        1710     Rb-  Rubidium, Ion     g   Rb-007
        >>> s = db.search('Ti')
        >>> print(len(s))
        88
        """

        formulasearch = self.db['formula'].str.contains(searchstr)
        namesearch = self.db['name'].str.contains(searchstr)

        return self.db[formulasearch | namesearch]

    def getphasedata(self, formula=None, name=None, phase=None, nocache=False):
        """
        Returns an element instance given the name of the element.
        formula, name and phase match the respective fields in the JANAF index.
        nocache = True means that we will always get the data from the web.

        >>> db = Janafdb()
        >>> db.getphasedata(formula='O2Ti', phase='cr')
        Traceback (most recent call last):
            ...
        ValueError: There are 2 records matching this pattern.
        >>> db.getphasedata(formula='Oxyz')
        Traceback (most recent call last):
            ...
        ValueError: Valid phase types are ['cr', 'l', 'cr,l', 'g', 'ref', 'cd', 'fl', 'am', 'vit', 'mon', 'pol', 'sln', 'aq', 'sat'].
        >>> db.getphasedata(formula='Oxyz', phase='l')
        Traceback (most recent call last):
            ...
        ValueError: Did not find Oxyz, None, (l)

        """

        # Check that the phase type requested is valid.
        validphasetypes = ['cr', 'l', 'cr,l', 'g', 'ref', 'cd', 'fl', 'am', 'vit', 'mon', 'pol', 'sln', 'aq', 'sat']
        if phase not in validphasetypes:
            raise ValueError("Valid phase types are " + str(validphasetypes) + ".")

        # We can search on either an exact formula, partial text match in the name, and exact phase type.
        formulasearch = pd.Series(np.ones(len(self.db)), dtype=bool)
        namesearch = formulasearch.copy()
        phasesearch = formulasearch.copy()
        if formula is not None:
            formulasearch = self.db['formula'] == formula
        if name is not None:
            namesearch = self.db['name'].str.contains(name)
        if phase is not None:
            phasesearch = self.db['phase'] == phase
        searchmatch = formulasearch & namesearch & phasesearch

        # Get the record (should be one record) which specifies this phase.
        PhaseRecord = self.db[searchmatch]
        if len(PhaseRecord) == 0:
            raise ValueError("Did not find %s, %s, (%s)" % (formula, name, phase))
        if len(PhaseRecord) > 1:
            raise ValueError("There are %d records matching this pattern."%len(PhaseRecord))

        # At this point we have one record.  Check if we have that file cached.
        cachedfilename = os.path.join(self.JANAF_cachedir, PhaseRecord['filename'].values[0]+'.txt')
        if os.path.exists(cachedfilename) and nocache==False:
            # Yes it was cached, so let's read it into memory.
            with open(cachedfilename, 'r') as f:
                textdata = f.read()
        else:
            # No it was not cached so let's get it from the web.
            response = urllib2.urlopen('http://kinetics.nist.gov/janaf/html/%s.txt'%PhaseRecord['filename'].values[0])
            textdata = response.read()

            # And cache the data so we aren't making unnecessary trips to the web.
            if nocache==False:
                with open(cachedfilename, 'w') as f:
                    f.write(textdata)

        # Create a phase class and return it.
        return JanafPhase(textdata)

    # def getmixturedata(self, components):
    #     """
    #     Creates a mixture of components given a list of tuples
    #     containing the formula and the volume percent
    #     """
    #     mixture = Mixture()
    #     for comp in components:
    #         mixture.add(self.getelementdata(comp[0]), comp[1])
    #
    #     return mixture


if __name__ == '__main__':
    db = Janafdb()

    s = db.search('Ti')
    print(len(s))

    print(db.getphasedata(formula='O2Ti', name='Rutile', phase='cr'))

    # mix = db.getmixturedata([("O2 REF ELEMENT", 20.9476),
    #                          ("N2  REF ELEMENT", 78.084),
    #                          ("CO2", 0.0319),
    #                          ("AR REF ELEMENT", 0.9365),
    #                          ("O2 REF ELEMENT", 1.2)])
    # mix.aggregate()

    # Test TiO phase

    # print(db.getelementdata('NiO  Solid-A'))
    # print(db.getelementdata('NiO  Solid-C'))
    # print(db.search('NiO'))
