/*
        Clifford attractor — hue-cycling parameter-sweep animation.

        xn+1 = sin(a yn) + c cos(a xn)
        yn+1 = sin(b xn) + d cos(b yn)

        Original author: Paul Richards
        Source: published on Paul Bourke's fractal page at
        http://paulbourke.net/fractals/clifford/paul_richards/main.cpp
        (The Clifford attractor family itself: Clifford A. Pickover.)

        This copy: kept unmodified from the original, with one addition —
        compile-time parameter overrides (g++ -DWIDTH=... -DITERS=...)
        so the sweep can be run cheaply without editing the source.

        License of this file: unknown (not stated in the original); kept
        here for reference / attribution. See README.md, Credits.
*/

#include <iostream>
#include <cmath>
#include <vector>

using namespace std;

// Change params only in this block
// Params can be overridden at compile time, e.g.:
//   g++ -O2 -DFRAMES=400 -DITERS=8000 clifford.cpp
#ifndef WIDTH
#define WIDTH 1600
#endif
#ifndef HEIGHT
#define HEIGHT 1200
#endif
#ifndef FRAMES
#define FRAMES 10000
#endif
#ifndef ITERS
#define ITERS 10000
#endif
#ifndef SKIP_ITERS
#define SKIP_ITERS 10
#endif

namespace {
    const int width = WIDTH;
    const int height = HEIGHT;
    const int frames = FRAMES;
    const int iters = ITERS;
    const int skipIters = SKIP_ITERS;

    double sensitivity = 0.02;
    
    const double minX = -4.0;
    const double minY = minX * height / width;

    const double maxX = 4.0;
    const double maxY = maxX * height / width;
    
    const double minA = acos( 1.6 / 2.0 );
    const double maxA = acos( 1.3 / 2.0 );
    
    const double minB = acos( -0.6 / 2.0 );
    const double maxB = acos( 1.7 / 2.0 );
    
    const double minC = acos( -1.2 / 2.0 );
    const double maxC = acos( 0.5 / 2.0 );
    
    const double minD = acos( 1.6 / 2.0 );
    const double maxD = acos( 1.4 / 2.0 );
};




class Color {
    public:
    
    double r, g, b;
    
    Color(const double &red = 0, const double &green = 0, const double &blue = 0) : r(red), g(green), b(blue) {
    }
    
    Color& operator+=(const Color &rhs) {
        r += rhs.r;
        g += rhs.g;
        b += rhs.b;
        return *this;
    }
    
    static Color createHue( double h ) {
        h *= 6.0;
        int hi = static_cast<int>( h );
        double hf = h - hi;
        
        
        switch( hi % 6 ) {
            case 0:
            return Color( 1.0 , hf, 0.0 );
            case 1:
            return Color( 1.0 - hf, 1.0, 0.0 );
            case 2:
            return Color( 0.0 , 1.0, hf );
            case 3:
            return Color( 0.0, 1.0 - hf, 1.0 );
            case 4:
            return Color( hf, 0.0, 1.0 );
            case 5:
            return Color( 1.0, 0.0, 1.0 - hf );
        }
        
        return Color();
    }
    

    Color operator+(const Color &rhs) const {
        return Color(*this) += rhs;
    }

    
};

int main(void) {
    
    vector<Color> image( width * height );
    
    for (int i = 0; i < frames; i++) {
        
        const double p = static_cast<double>(i) / frames;
        const double a = cos( minA + p * (maxA - minA) ) * 2.0;
        const double b = cos( minB + p * (maxB - minB) ) * 2.0;
        const double c = cos( minC + p * (maxC - minC) ) * 2.0;
        const double d = cos( minD + p * (maxD - minD) ) * 2.0;

        const Color curCol = Color::createHue( p ); 
        
        double x = 0.0, y = 0.0;
        
        for (int j = 0; j < iters; j++) {
        
            double xn = sin(a * y) + c * cos(a * x);
            double yn = sin(b * x) + d * cos(b * y);
            x = xn;
            y = yn;
            
            if ( j < skipIters )
                continue;
            
            
            int xi = static_cast<int>( (x - minX) * width / (maxX - minX) );
            int yi = static_cast<int>( (y - minY) * height / (maxY - minY) );
            if ( xi >= 0 && xi < width &&
                 yi >= 0 && yi < height ) {
                 
                 image[ xi + yi * width ] += curCol;
                 
            }
              
        }
        clog << "\r" << i;
    
    }
    clog << "\n";
    
    cout
        << "P6\n"
        << width << " " << height << "\n"
        << "255\n";
        
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            Color &c = image[ x + y * width ];
            
            unsigned char r = static_cast<unsigned char>( (1.0 - exp( -sensitivity * c.r )) * 255.0 );
            unsigned char g = static_cast<unsigned char>( (1.0 - exp( -sensitivity * c.g )) * 255.0 );
            unsigned char b = static_cast<unsigned char>( (1.0 - exp( -sensitivity * c.b )) * 255.0 );
            
            cout << r << g << b;
        }
    }
    
    
    return 0;
}
