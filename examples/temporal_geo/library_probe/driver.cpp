#include "smoke.h"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>

void require(bool ok, const char *label) {
    if (!ok) throw std::runtime_error(label);
}

int main() {
    try {
        int instant_order[3], date_order[3], within[2];
        require(smoke_instant_compare(1000000,1000001,&instant_order[0]) == 0, "instant before");
        require(smoke_instant_compare(1000001,1000000,&instant_order[1]) == 0, "instant after");
        require(smoke_instant_compare(1000000,1000000,&instant_order[2]) == 0, "instant equal");
        require(smoke_date_compare(2024,2,29,2024,3,1,&date_order[0]) == 0, "date before");
        require(smoke_date_compare(2024,3,1,2024,2,29,&date_order[1]) == 0, "date after");
        require(smoke_date_compare(2024,2,29,2024,2,29,&date_order[2]) == 0, "date equal");
        for (int i=0;i<3;++i) {
            const int expected = i == 0 ? -1 : i == 1 ? 1 : 0;
            require(instant_order[i] == expected && date_order[i] == expected, "ordering");
        }
        int sentinel = 77;
        const int invalid_date = smoke_date_compare(2023,2,29,2024,3,1,&sentinel);
        require(invalid_date == 1 && sentinel == 77, "invalid date rejected");
        double distance = 0, geodesic = 0;
        require(smoke_distance(0,0,30,40,&distance) == 0 && distance == 50, "GEOS distance");
        require(smoke_dwithin(0,0,30,40,50,&within[0]) == 0 && within[0] == 1, "inclusive radius");
        require(smoke_dwithin(0,0,30,40,49,&within[1]) == 0 && within[1] == 0, "outside radius");
        require(smoke_geodesic(0,0,0,1,&geodesic) == 0 &&
                std::abs(geodesic-111319.49079327357) < 1e-6, "WGS84 inverse");
        const int negative_radius = smoke_dwithin(0,0,30,40,-1,&sentinel);
        const int null_output = smoke_instant_compare(0,1,nullptr);
        double unchanged = 77;
        const int invalid_latitude = smoke_geodesic(91,0,0,1,&unchanged);
        require(negative_radius == 1 && null_output == 1 && invalid_latitude == 1 &&
                sentinel == 77 && unchanged == 77, "argument status checks");
        std::cout << std::setprecision(17)
          << "{\"date_version\":\"" << smoke_date_version()
          << "\",\"geos_version\":\"" << smoke_geos_version()
          << "\",\"proj_version\":\"" << smoke_proj_version()
          << "\",\"instant_order\":[" << instant_order[0] << ',' << instant_order[1] << ',' << instant_order[2]
          << "],\"date_order\":[" << date_order[0] << ',' << date_order[1] << ',' << date_order[2]
          << "],\"invalid_date_status\":" << invalid_date
          << ",\"projected_distance_metres\":" << distance
          << ",\"dwithin_50_49\":[" << within[0] << ',' << within[1]
          << "],\"geodesic_metres\":" << geodesic
          << ",\"negative_radius_status\":" << negative_radius
          << ",\"null_output_status\":" << null_output
          << ",\"invalid_latitude_status\":" << invalid_latitude << "}\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
