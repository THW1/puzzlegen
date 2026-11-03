# Third-party notices

## Hat and Spectre substitution systems (`src/puzzlegen/tilings/_kaplan.py`)

`_kaplan.py` is adapted from **hat-amp 0.2.0** by Newton Winter
(<https://github.com/winternewt/hat-amp>), which ported the substitution systems from
Craig S. Kaplan's reference implementations:

- **hatviz** (hat tiling, H/T/P/F metatiles): <https://github.com/isohedral/hatviz>,
  BSD 3-Clause licence (text below).
- **Spectre app** (Spectre tiling): <https://cs.uwaterloo.ca/~csk/spectre/>.
  *Caveat:* no public repository or licence text for the Spectre app could be found
  when this code was vendored (November 2026); the hat-amp port itself is MIT-licensed.
  Remove `spectre_patch` and the `spectre` tiling if this matters for your use.

Changes: geometry helpers inlined, tree walks also return each tile's path, unused API
removed, hats taken from the H metatile instead of the intermediate patch (which holds
overlapping scaffolding tiles).

### hat-amp — MIT License

```
MIT License

Copyright (c) 2026 Newton Winter

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### hatviz — BSD 3-Clause License

```
BSD 3-Clause License

Copyright (c) 2023, Craig S. Kaplan

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Runtime dependencies (not vendored)

numpy, scipy, shapely, manifold3d; optional: svgelements (MIT) for SVG regions.
