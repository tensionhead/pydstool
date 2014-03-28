#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import

from PyDSTool.common import intersect, concatStrDict, idfn
from PyDSTool.parseUtils import addArgToCalls
from PyDSTool.Symbolic import QuantSpec

from .base import _processReused, CodeGenerator


MATLAB_FUNCTION_TEMPLATE = """\
function [vf_, y_] = {name}(vf_, t_, x_, p_)
% Vector field definition for model {specname}
% Generated by PyDSTool for ADMC++ target

{pardef}{vardef}
{start}{reuseterms}
{result}

{end}
"""


MATLAB_AUX_TEMPLATE = """\
function y_ = {name}({vnames},  p_)
% Auxilliary function {name} for model {specname}
% Generated by PyDSTool for ADMC++ target

{pardef} \


{reuseterms}
y_ = {result};

"""


class Matlab(CodeGenerator):

    def __init__(self, fspec, **kwargs):
        if 'define' not in kwargs:
            kwargs['define'] = "\t{0} = {1}_({2});\n"

        if 'power_sign' not in kwargs:
            kwargs['power_sign'] = "^"

        super(Matlab, self).__init__(fspec, **kwargs)

    def generate_auxfun(self, name, auxspec, pars=None):

        if pars is None:
            pars = self.fspec.pars
        vnames = dict((v, v + '__') for v in auxspec[0])
        spec = self._normalize_spec(auxspec[1])
        body, reusestr = self._process_reused(name, spec, vnames)
        code = self._render(
            MATLAB_AUX_TEMPLATE,
            {
                'name': name,
                'specname': self.fspec.name,
                'vnames': ', '.join([vnames[v] for v in auxspec[0]]),
                'pardef': "\n% Parameter definitions\n\n" + self.defineMany(pars, "p", 1),
                'reuseterms': (len(reusestr) > 0) * "\n% reused term definitions \n" + reusestr.strip() + (len(reusestr) > 0) * "\n",
                'result': body,
            }
        )
        return code, '\n'.join(code.split('\n')[:5])

    def generate_special(self, name, spec):
        raise NotImplementedError

    def _render(self, template, context):
        return template.format(**context)

    def _process_reused(self, name, spec, vnames):
        reusestr, processed = self._processReusedMatlab([name], {name: spec})
        auxQ = QuantSpec('aux', processed[name], treatMultiRefs=False)
        auxQ.mapNames(vnames)
        reuseQ = QuantSpec('reuse', reusestr, preserveSpace=True)
        # TODO: uncomment to add name mangling in reuseterms
        # reuseQ.mapNames(vnames)
        return auxQ(), reuseQ() if reusestr else ''

    def generate_spec(self, specname_vars, specs):
        name = 'vfield'
        for specstr in specs.itervalues():
            specstr = self._normalize_spec(specstr)
        reusestr, specupdated = self._processReusedMatlab(specname_vars, specs)
        result = []
        for i, it in enumerate(specname_vars):
            specstr = "y_(" + str(i + 1) + ") = " + self._processIfMatlab(specupdated[it]) + ';'
            if self.fspec.auxfns:
                specstr = addArgToCalls(specstr, self.fspec.auxfns.keys(), "p_")
            result.append(specstr)

        code = self._render(
            MATLAB_FUNCTION_TEMPLATE,
            {
                'name': name,
                'specname': self.fspec.name,
                'pardef': "\n% Parameter definitions\n\n" + self.defineMany(self.fspec.pars, "p", 1),
                'vardef': "\n% Variable definitions\n\n" + self.defineMany(specname_vars, "x", 1),
                'start': self._format_user_code(self.opts['start']) if self.opts['start'] else '',
                'result': '\n'.join(result),
                'reuseterms': (len(reusestr) > 0) * "% reused term definitions \n" + reusestr,
                'end': self._format_user_code(self.opts['end']) if self.opts['end'] else '',
            }
        )

        return (code, name)

    def _processIfMatlab(self, specStr):
        # NEED TO CHECK WHETHER THIS IS NECESSARY AND WORKS
        # IF STATEMENTS LOOK DIFFERENT IN MATLAB
        qspec = QuantSpec('spec', specStr)
        qtoks = qspec[:]
        if 'if' in qtoks:
            raise NotImplementedError
        else:
            new_specStr = specStr
        return new_specStr

    def _processReusedMatlab(self, specnames, specdict):
        """Process reused subexpression terms for Matlab code."""

        # must add parameter argument so that we can name
        # pars inside the functions! this would either
        # require all calls to include this argument (yuk!) or
        # else we add these extra pars automatically to
        # every call found in the .c code (as is done currently.
        # this is still an untidy solution, but there you go...)
        parseFunc = idfn
        if self.fspec.auxfns:
            parseFunc = lambda s: addArgToCalls(s, self.fspec.auxfns.keys(), "p_")
        reused, specupdated, new_protected, order = _processReused(specnames,
                                                                   specdict,
                                                                   self.fspec.reuseterms,
                                                                   '', '', ';',
                                                                   parseFunc)
        self.fspec._protected_reusenames = new_protected
        reusedefs = {}.fromkeys(new_protected)
        for _, deflist in reused.iteritems():
            for d in deflist:
                reusedefs[d[2]] = d
        return (concatStrDict(reusedefs, intersect(order, reusedefs.keys())),
                specupdated)

    def _format_user_code(self, code):
        before = '% Verbose code insert -- begin '
        after = '% Verbose code insert -- end \n\n'
        return self._format_code(code, before, after)
