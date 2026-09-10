#include "native_domains.h"
#include "vendor/date/date.h"
#include <cmath>
#include <array>
#include <map>
#include <set>
#include <vector>
#include <sstream>
#include <locale>
#include <cstring>
#include <limits>
#include <new>
#include <stdexcept>
#include <string>
#ifdef DLP_HAVE_GEODESIC
#include "vendor/geographiclib/geodesic.h"
#define DLP_STRINGIFY_INNER(value) #value
#define DLP_STRINGIFY(value) DLP_STRINGIFY_INNER(value)
#endif

namespace {
using Wide = __int128;
constexpr int64_t SECOND = 1000000, DAY = 86400 * SECOND, EPOCH_ORDINAL = 719163;
constexpr int64_t LOW = std::numeric_limits<int64_t>::min();
constexpr int64_t HIGH = std::numeric_limits<int64_t>::max();
enum { BOOL=1, INTEGER, DECIMAL, FLOAT, DATE, INSTANT, TIME, DURATION, POINT, INTERVAL,
       POLICY, QUANTITY, UNIT };
struct Failure { int status; };
thread_local char last_error[256] = "";
void require(bool good, int code) { if (!good) throw Failure{code}; }
int64_t checked(Wide value) {
    require(value >= LOW && value <= HIGH, 3);
    return static_cast<int64_t>(value);
}
Wide magnitude(Wide value) { return value < 0 ? -value : value; }
Wide power10(unsigned scale) {
    require(scale <= 36, 3);
    Wide value=1;
    for (unsigned i=0; i<scale; ++i) value *= 10;
    return value;
}
Wide gcd(Wide left, Wide right) {
    left=magnitude(left); right=magnitude(right);
    while (right) { const Wide next=left%right; left=right; right=next; }
    return left;
}
dlp_domain_value integer(int64_t value) {
    dlp_domain_value out{}; out.tag=INTEGER; out.a=value; return out;
}
dlp_domain_value boolean(bool value) {
    dlp_domain_value out{}; out.tag=BOOL; out.a=value; return out;
}
dlp_domain_value decimal(Wide coefficient, unsigned scale) {
    if (!coefficient) scale=0;
    while (scale && coefficient && coefficient%10 == 0) { coefficient/=10; --scale; }
    require(scale <= 18, 4);
    dlp_domain_value out{}; out.tag=DECIMAL; out.a=checked(coefficient); out.b=scale;
    return out;
}
dlp_domain_value fraction(Wide numerator, Wide denominator) {
    require(denominator != 0, 2);
    if (denominator < 0) { denominator=-denominator; numerator=-numerator; }
    const Wide factor=gcd(numerator, denominator);
    numerator/=factor; denominator/=factor;
    unsigned twos=0, fives=0;
    while (denominator%2 == 0) { denominator/=2; ++twos; }
    while (denominator%5 == 0) { denominator/=5; ++fives; }
    const unsigned scale=twos>fives ? twos : fives;
    require(denominator == 1 && scale <= 18, 4);
    checked(numerator); // multiplying the reduced numerator cannot reduce magnitude
    for (unsigned i=twos; i<scale; ++i) numerator*=2;
    for (unsigned i=fives; i<scale; ++i) numerator*=5;
    return decimal(numerator, scale);
}
bool numeric(const dlp_domain_value &v) { return v.tag==INTEGER || v.tag==DECIMAL; }
bool temporal(const dlp_domain_value &v) { return v.tag>=DATE && v.tag<=DURATION; }
date::year_month_day calendar(const dlp_domain_value &v) {
    return date::year{static_cast<int>(v.a)}/date::month{static_cast<unsigned>(v.b)}
        /date::day{static_cast<unsigned>(v.c)};
}
int64_t key(const dlp_domain_value &v) {
    return v.tag==DATE ? date::sys_days{calendar(v)}.time_since_epoch().count()+EPOCH_ORDINAL : v.a;
}
void validate(const dlp_domain_value &v) {
    require(v.reserved==0 && v.tag>=BOOL && v.tag<=UNIT, 1);
    switch(v.tag) {
    case BOOL: require(v.a==0 || v.a==1, 2); break;
    case DECIMAL: require(v.b>=0 && v.b<=18, 4); break;
    case FLOAT: require(std::isfinite(v.x), 2); break;
    case DATE:
        require(v.a>=1 && v.a<=9999 && v.b>=1 && v.b<=12 && v.c>=1 && v.c<=31, 2);
        require(calendar(v).ok(), 2); break;
    case TIME: require(v.a>=0 && v.a<DAY, 2); break;
    case POINT:
        require(std::isfinite(v.x) && std::isfinite(v.y) && v.x>=-180 && v.x<=180
                && v.y>=-90 && v.y<=90, 2); break;
    case INTERVAL:
        require(v.c==DATE || v.c==INSTANT, 1);
        require(v.a<v.b, 2);
        if (v.c==DATE) require(v.a>=1 && v.b<=3652059, 2);
        break;
    case POLICY: require(v.a==1, 5); break;
    case QUANTITY:
        require(v.c==INTEGER || v.c==DECIMAL, 1);
        require(v.b>=0 && v.b<=18, 4);
        require(v.x==1 || v.x==2 || v.x==3, 5); break;
    case UNIT: require(v.a>=1 && v.a<=3, 5); break;
    default: break;
    }
}
unsigned arity(uint32_t op) {
    if (op==30) return 1;
    if (op==4 || op==42) return 3;
    if ((op>=1 && op<=10) || (op>=20 && op<=28) || (op>=31 && op<=37)
            || op==40 || op==41) return 2;
    throw Failure{5};
}
double coordinate(const dlp_domain_value &v) {
    require(numeric(v) || v.tag==FLOAT, 1);
    double result=v.x;
    if (v.tag!=FLOAT) {
        // One correctly rounded decimal-to-binary conversion, not a rounded
        // coefficient conversion followed by a second rounded floating division.
        const std::string text=std::to_string(v.a)+"e-"+std::to_string(v.tag==DECIMAL ? v.b : 0);
        // Floating from_chars is unavailable before iOS 26 in Apple's libc++.
        // The classic locale keeps decimal syntax independent of host locale.
        std::istringstream stream(text);
        stream.imbue(std::locale::classic());
        stream >> result;
        require(!stream.fail() && stream.eof(), 2);
    }
    require(std::isfinite(result), 2);
    return result;
}
double distance(const dlp_domain_value &a, const dlp_domain_value &b) {
    require(a.tag==POINT && b.tag==POINT, 1);
#ifdef DLP_HAVE_GEODESIC
    static const geod_geodesic ellipsoid=[] {
        geod_geodesic value; geod_init(&value, 6378137.0, 1.0/298.257223563); return value;
    }();
    double metres=0;
    geod_inverse(&ellipsoid, a.y, a.x, b.y, b.x, &metres, nullptr, nullptr);
    require(std::isfinite(metres) && metres>=0, 7);
    return metres;
#else
    (void)a; (void)b;
    throw Failure{5};
#endif
}
dlp_domain_value evaluate(uint32_t op, const dlp_domain_value *row) {
    if (op==30) { dlp_domain_value out{}; out.tag=FLOAT; out.x=coordinate(row[0]); return out; }
    const auto &a=row[0], &b=row[1];
    if (op==32) {
        require(numeric(a) && b.tag==UNIT, 1);
        auto out=a; out.tag=QUANTITY; out.c=a.tag; out.x=static_cast<double>(b.a); return out;
    }
    if (op>=33 && op<=37) {
        require(a.tag==QUANTITY && b.tag==QUANTITY && a.x==b.x, 1);
        dlp_domain_value inner[2]={a,b};
        inner[0].tag=static_cast<uint32_t>(a.c); inner[1].tag=static_cast<uint32_t>(b.c);
        const uint32_t operation=op==33 ? 20 : op==34 ? 21 : op==35 ? 24 : op==36 ? 26 : 23;
        auto out=evaluate(operation, inner);
        if (op==33 || op==34) { out.c=out.tag; out.tag=QUANTITY; out.x=a.x; }
        return out;
    }
    if (op==31) { require(a.tag==FLOAT && b.tag==FLOAT, 1); return boolean(a.x<=b.x); }
    if (op>=1 && op<=3) {
        require(temporal(a) && a.tag==b.tag, 1);
        return boolean(op==1 ? key(a)<key(b) : op==2 ? key(a)>key(b) : key(a)==key(b));
    }
    if (op==4) {
        require(a.tag==DATE && b.tag==DATE && row[2].tag==POLICY, 1);
        require(key(b)>=key(a), 2);
        return integer(b.a-a.a-((b.b<a.b) || (b.b==a.b && b.c<a.c)));
    }
    if (op==5) {
        require((a.tag==DATE || a.tag==INSTANT) && a.tag==b.tag, 1);
        dlp_domain_value out{}; out.tag=INTERVAL; out.a=key(a); out.b=key(b); out.c=a.tag;
        validate(out); return out;
    }
    if (op==6) {
        require(a.tag==INTERVAL && b.tag==a.c, 1);
        return boolean(a.a<=key(b) && key(b)<a.b);
    }
    if (op==7 || op==8) {
        require(a.tag==INTERVAL && b.tag==INTERVAL && a.c==b.c, 1);
        return boolean(op==8 ? a.b==b.a : a.a<b.b && b.a<a.b);
    }
    if (op==9) {
        require(temporal(a) && b.tag==DURATION, 1);
        auto out=a;
        if (a.tag==DATE) {
            require(b.a%DAY==0, 2);
            const Wide ordinal=static_cast<Wide>(key(a))+b.a/DAY;
            require(ordinal>=1 && ordinal<=3652059, 3);
            const date::year_month_day result{date::sys_days{date::days{
                static_cast<int>(ordinal-EPOCH_ORDINAL)}}};
            out.a=static_cast<int>(result.year()); out.b=static_cast<unsigned>(result.month());
            out.c=static_cast<unsigned>(result.day());
        } else out.a=checked(static_cast<Wide>(a.a)+b.a);
        validate(out); return out;
    }
    if (op==10) {
        require(a.tag==INSTANT && b.tag==INSTANT, 1);
        return fraction(static_cast<Wide>(b.a)-a.a, SECOND);
    }
    if (op>=20 && op<=28) {
        require(numeric(a) && numeric(b), 1);
        const unsigned sa=a.tag==DECIMAL ? static_cast<unsigned>(a.b) : 0;
        const unsigned sb=b.tag==DECIMAL ? static_cast<unsigned>(b.b) : 0;
        const Wide left=static_cast<Wide>(a.a)*power10(sb), right=static_cast<Wide>(b.a)*power10(sa);
        if (op>=24) return boolean(op==24 ? left==right : op==25 ? left<right
                                   : op==26 ? left<=right : op==27 ? left>right : left>=right);
        if (op==23) return fraction(left, right);
        if (a.tag==INTEGER && b.tag==INTEGER) {
            const Wide value=op==20 ? static_cast<Wide>(a.a)+b.a : op==21
                ? static_cast<Wide>(a.a)-b.a : static_cast<Wide>(a.a)*b.a;
            return integer(checked(value));
        }
        if (op==22) return decimal(static_cast<Wide>(a.a)*b.a, sa+sb);
        const unsigned scale=sa>sb ? sa : sb;
        const Wide first=static_cast<Wide>(a.a)*power10(scale-sa);
        const Wide second=static_cast<Wide>(b.a)*power10(scale-sb);
        return decimal(op==20 ? first+second : first-second, scale);
    }
    if (op==40) {
        dlp_domain_value out{}; out.tag=POINT; out.x=coordinate(a); out.y=coordinate(b);
        validate(out); return out;
    }
    if (op==41 || op==42) {
        double radius=0;
        if (op==42) { radius=coordinate(row[2]); require(radius>=0, 2); }
        const double metres=distance(a,b);
        if (op==42) return boolean(metres<=radius);
        dlp_domain_value out{}; out.tag=FLOAT; out.x=metres; return out;
    }
    throw Failure{5};
}
} // namespace

extern "C" uint32_t dlp_domain_abi_version(void) { return 1; }
extern "C" uint32_t dlp_domain_capabilities(void) {
#ifdef DLP_HAVE_GEODESIC
    return 1;
#else
    return 0;
#endif
}
extern "C" const char *dlp_domain_geodesic_version(void) {
#ifdef DLP_HAVE_GEODESIC
    return "GeographicLib-C-" DLP_STRINGIFY(GEODESIC_VERSION_MAJOR) "."
        DLP_STRINGIFY(GEODESIC_VERSION_MINOR) "." DLP_STRINGIFY(GEODESIC_VERSION_PATCH);
#else
    return "unavailable";
#endif
}
extern "C" const char *dlp_domain_last_error(void) { return last_error; }
extern "C" int dlp_domain_evaluate(uint32_t opcode, const dlp_domain_value *inputs,
                                   size_t rows, size_t columns, dlp_domain_value *outputs,
                                   int32_t *statuses) {
    last_error[0]='\0';
    if ((rows && (!inputs || !outputs || !statuses)) || columns>3
            || (columns && rows>std::numeric_limits<size_t>::max()/columns)
            || (columns && rows>std::numeric_limits<size_t>::max()/columns/sizeof(dlp_domain_value))
            || rows>std::numeric_limits<size_t>::max()/sizeof(dlp_domain_value)) {
        std::strcpy(last_error, "Invalid native domain batch buffers/dimensions"); return -1;
    }
    for (size_t i=0; i<rows; ++i) {
        outputs[i]={}; statuses[i]=0;
        try {
            require(columns==arity(opcode), 8);
            const auto *row=inputs+i*columns;
            for (size_t c=0; c<columns; ++c) validate(row[c]);
            outputs[i]=evaluate(opcode,row);
        } catch (const Failure &failure) { statuses[i]=failure.status; }
        catch (const std::bad_alloc &) { statuses[i]=6; }
        catch (...) { statuses[i]=7; }
    }
    return 0;
}

namespace {
using ValueKey=std::array<unsigned char,sizeof(dlp_domain_value)>;
thread_local int32_t context_status=0;
dlp_domain_value canonical_value(const dlp_domain_value&v) {
    validate(v);
    dlp_domain_value out{}; out.tag=v.tag;
    switch(v.tag) {
    case DECIMAL: return decimal(v.a,static_cast<unsigned>(v.b));
    case FLOAT: out.x=v.x; break;
    case DATE: case INTERVAL: out.a=v.a;out.b=v.b;out.c=v.c;break;
    case POINT: out.x=v.x;out.y=v.y;break;
    case QUANTITY:
        require(v.c!=INTEGER || v.b==0,1);
        out.a=v.a;out.b=v.b;out.c=v.c;out.x=v.x;
        if(v.c==DECIMAL){const auto normalized=decimal(v.a,static_cast<unsigned>(v.b));out.a=normalized.a;out.b=normalized.b;}
        break;
    default: out.a=v.a;break;
    }
    return out;
}
ValueKey value_key(const dlp_domain_value&v){ValueKey key{};std::memcpy(key.data(),&v,sizeof v);return key;}
template<class F>int context_api(F action)noexcept{
    context_status=0;last_error[0]=0;
    try{action();return 0;}
    catch(const Failure&failure){context_status=failure.status;}
    catch(const std::bad_alloc&){context_status=6;}
    catch(...){context_status=7;}
    const char*names[]={"OK","TYPE_ERROR","DOMAIN_ERROR","OVERFLOW","INEXACT",
                        "UNAVAILABLE","RESOURCE_LIMIT","INTERNAL_ERROR","ARITY_ERROR"};
    std::strncpy(last_error,names[context_status>=0&&context_status<=8?context_status:7],sizeof(last_error)-1);
    return -1;
}
}
struct dlp_domain_context {
    uint64_t next=1;
    std::map<uint64_t,dlp_domain_value> values;
    std::map<ValueKey,uint64_t> ids;
    dlp_domain_context_stats stats{};
    explicit dlp_domain_context(uint64_t capacity){stats.capacity=capacity;stats.generation=1;}
    uint64_t intern(const dlp_domain_value&v){
        const auto key=value_key(v);auto old=ids.find(key);if(old!=ids.end()){++stats.intern_hits;return old->second;}
        require(values.size()<stats.capacity&&next<std::numeric_limits<uint64_t>::max(),6);
        const uint64_t id=next++;
        auto entry=ids.emplace(key,id);
        try{values.emplace(id,v);}catch(...){ids.erase(entry.first);throw;}
        return id;
    }
};
extern "C" int32_t dlp_domain_context_last_status(){return context_status;}
extern "C" int dlp_domain_context_new(uint64_t capacity,dlp_domain_context**out){
    if(out)*out=nullptr;
    return context_api([&]{require(out&&capacity,1);*out=new dlp_domain_context(capacity);});
}
extern "C" void dlp_domain_context_free(dlp_domain_context*context){delete context;}
extern "C" int dlp_domain_context_clear(dlp_domain_context*context){return context_api([&]{
    require(context,1);context->values.clear();context->ids.clear();++context->stats.generation;++context->stats.clears;
});}
extern "C" int dlp_domain_context_intern(dlp_domain_context*context,const dlp_domain_value*input,
                                          size_t count,uint64_t*ids){return context_api([&]{
    require(context&&(!count||(input&&ids))&&count<=std::numeric_limits<size_t>::max()/sizeof(dlp_domain_value),1);
    std::vector<dlp_domain_value> canonical;canonical.reserve(count);std::set<ValueKey> missing;
    for(size_t i=0;i<count;++i){canonical.push_back(canonical_value(input[i]));auto key=value_key(canonical.back());if(!context->ids.count(key))missing.insert(key);}
    require(missing.size()<=context->stats.capacity-context->values.size(),6);
    context->stats.transferred_inputs+=count;context->stats.intern_requests+=count;
    for(size_t i=0;i<count;++i)ids[i]=context->intern(canonical[i]);
});}
extern "C" int dlp_domain_context_get(dlp_domain_context*context,const uint64_t*ids,size_t count,
                                       dlp_domain_value*values,int32_t*statuses){return context_api([&]{
    require(context&&(!count||(ids&&values&&statuses))&&count<=std::numeric_limits<size_t>::max()/sizeof(dlp_domain_value),1);
    for(size_t i=0;i<count;++i){values[i]={};auto found=context->values.find(ids[i]);statuses[i]=found==context->values.end()?1:0;if(!statuses[i]){values[i]=found->second;++context->stats.transferred_outputs;}}
});}
extern "C" int dlp_domain_context_evaluate(dlp_domain_context*context,uint32_t opcode,
                                            const uint64_t*inputs,size_t rows,size_t columns,
                                            uint64_t*outputs,int32_t*statuses){return context_api([&]{
    require(context&&(!rows||(inputs&&outputs&&statuses))&&columns<=3,1);
    require(!columns||rows<=std::numeric_limits<size_t>::max()/columns/sizeof(uint64_t),1);
    require(rows<=std::numeric_limits<size_t>::max()/sizeof(dlp_domain_value),1);
    std::vector<dlp_domain_value> computed(rows);std::vector<int32_t> result_status(rows);std::set<ValueKey> missing;
    for(size_t i=0;i<rows;++i){
        try{require(columns==arity(opcode),8);dlp_domain_value args[3]{};
            for(size_t column=0;column<columns;++column){auto found=context->values.find(inputs[i*columns+column]);require(found!=context->values.end(),1);args[column]=found->second;}
            computed[i]=canonical_value(evaluate(opcode,args));auto key=value_key(computed[i]);if(!context->ids.count(key))missing.insert(key);
        }catch(const Failure&failure){result_status[i]=failure.status;}
        catch(const std::bad_alloc&){result_status[i]=6;}
        catch(...){result_status[i]=7;}
    }
    require(missing.size()<=context->stats.capacity-context->values.size(),6);
    for(size_t i=0;i<rows;++i){statuses[i]=result_status[i];outputs[i]=statuses[i]?0:context->intern(computed[i]);}
    context->stats.evaluated_rows+=rows;
});}
extern "C" int dlp_domain_context_get_stats(dlp_domain_context*context,dlp_domain_context_stats*out){return context_api([&]{
    require(context&&out,1);*out=context->stats;out->retained_values=context->values.size();
});}
extern "C" int dlp_domain_context_compare(dlp_domain_context*context,uint64_t left,uint64_t right,int32_t*out){return context_api([&]{
    require(context&&out,1);auto l=context->values.find(left),r=context->values.find(right);
    require(l!=context->values.end()&&r!=context->values.end(),1);
    auto a=l->second,b=r->second;
    if(a.tag==QUANTITY&&b.tag==QUANTITY){require(a.x==b.x,1);a.tag=static_cast<uint32_t>(a.c);b.tag=static_cast<uint32_t>(b.c);}
    if(numeric(a)&&numeric(b)){
        const unsigned sa=a.tag==DECIMAL?static_cast<unsigned>(a.b):0,sb=b.tag==DECIMAL?static_cast<unsigned>(b.b):0;
        const Wide av=static_cast<Wide>(a.a)*power10(sb),bv=static_cast<Wide>(b.a)*power10(sa);
        *out=av<bv?-1:av>bv?1:0;
    }else if(a.tag==FLOAT&&b.tag==FLOAT){*out=a.x<b.x?-1:a.x>b.x?1:0;}
    else{require(temporal(a)&&a.tag==b.tag,1);const auto av=key(a),bv=key(b);*out=av<bv?-1:av>bv?1:0;}
});}
