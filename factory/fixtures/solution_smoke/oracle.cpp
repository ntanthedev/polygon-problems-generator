#include <iostream>
#include <array>
#include <numeric>
int main(){ long long a,b; if(!(std::cin>>a>>b))return 1; std::array<long long,2> v{a,b}; std::cout<<std::accumulate(v.begin(),v.end(),0LL)<<'\n'; }
