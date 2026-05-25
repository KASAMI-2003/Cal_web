#!/bin/bash
HTEM anisotropy -modulus B -plt png -read Elasticity_0K.dat
HTEM anisotropy -modulus G -plt png -read Elasticity_0K.dat
HTEM anisotropy -modulus E -plt png -read Elasticity_0K.dat
HTEM anisotropy -modulus nu -plt png -read Elasticity_0K.dat
HTEM anisotropy -modulus sound -plt png -read Elasticity_0K.dat
HTEM anisotropy -modulus gif
